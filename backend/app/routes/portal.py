"""Customer-only API: separate sessions, scoped records, public messages only."""
import secrets
from datetime import timedelta
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlmodel import select
from sqlalchemy import func
from ..dependencies import DB, token_hash
from ..models import Admin, CustomerSession, LoginSession, Ticket, TicketRevision, TicketMessage, Workspace, AuditEvent, now
from ..schemas import TicketCreate, CustomerFollowup
from ..jobs import enqueue
from ..services.usage import consume
from ..services.resolution import REASONS


def customer(request: Request, session: DB, csrf: Annotated[str | None, Header(alias='X-Customer-CSRF')] = None):
    if not request.app.state.settings.customer_portal_enabled:
        raise HTTPException(404, 'The customer portal is disabled.')
    token = request.cookies.get('support_session')
    identity = session.get(CustomerSession, token_hash(token)) if token else None
    if not identity or identity.expires_at <= now():
        raise HTTPException(401, 'Start a support session to continue.')
    workspace = session.get(Workspace, identity.workspace_id)
    if not workspace or (workspace.expires_at and workspace.expires_at <= now()):
        raise HTTPException(401, 'This support workspace has expired.')
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        if not secrets.compare_digest(csrf or '', identity.csrf_token):
            raise HTTPException(403, 'Refresh the support portal before making changes.')
        consume(session, 'customer:writes:global', 300, 86400)
        consume(session, 'customer:writes:' + identity.customer_id, 50, 3600)
        session.commit()
    return identity


Customer = Annotated[CustomerSession, Depends(customer)]


def owned(session, identity, identifier):
    ticket = session.exec(select(Ticket).where(Ticket.id == identifier,
        Ticket.workspace_id == identity.workspace_id, Ticket.customer_id == identity.customer_id).with_for_update()).first()
    if not ticket:
        raise HTTPException(404, 'Enquiry not found.')
    return ticket


def public_ticket(ticket):
    return {key: getattr(ticket, key) for key in ['id', 'subject', 'body', 'status', 'resolution_state',
        'outcome_version', 'answer', 'created_at', 'updated_at']}


def public_detail(session, ticket):
    return {'ticket': public_ticket(ticket), 'messages': session.exec(select(TicketMessage).where(
        TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at, TicketMessage.id)).all()}


def register(app):
    router = APIRouter(prefix='/api/portal')

    @router.post('/session')
    def start(request: Request, response: Response, session: DB):
        if not app.state.settings.customer_portal_enabled:
            raise HTTPException(404, 'The customer portal is disabled.')
        # An authenticated operator may preview only their own workspace.
        workspace = 1
        admin_token = request.cookies.get('triage_session')
        login = session.get(LoginSession, token_hash(admin_token)) if admin_token else None
        if login and login.expires_at > now():
            admin = session.get(Admin, login.admin_id)
            member = session.get(Workspace, login.workspace_id)
            if (admin and member and (admin.username != 'demo' or app.state.settings.public_demo_enabled)
                    and (not member.expires_at or member.expires_at > now())):
                workspace = login.workspace_id
        token = request.cookies.get('support_session')
        identity = session.get(CustomerSession, token_hash(token)) if token else None
        if not identity or identity.expires_at <= now() or identity.workspace_id != workspace:
            consume(session, 'customer:sessions:global', 100, 86400)
            consume(session, 'customer:sessions:client:' + token_hash(request.client.host if request.client else 'unknown'), 15, 3600)
            token = secrets.token_urlsafe(32)
            identity = CustomerSession(token_hash=token_hash(token), customer_id=uuid4().hex,
                workspace_id=workspace, csrf_token=secrets.token_urlsafe(32),
                expires_at=now() + timedelta(hours=app.state.settings.session_hours))
            session.add(identity)
            session.commit()
        response.set_cookie('support_session', token, httponly=True, secure=app.state.settings.cookie_secure,
                            samesite='strict', path='/api/portal', max_age=app.state.settings.session_hours * 3600)
        return {'csrf_token': identity.csrf_token, 'expires_at': identity.expires_at, 'is_demo': workspace != 1}

    @router.delete('/session')
    def end(response: Response, session: DB, identity: Customer):
        session.delete(identity)
        session.commit()
        response.delete_cookie('support_session', path='/api/portal')
        return {'ok': True}

    @router.get('/tickets')
    def tickets(session: DB, identity: Customer):
        rows = session.exec(select(Ticket).where(Ticket.customer_id == identity.customer_id,
            Ticket.workspace_id == identity.workspace_id).order_by(Ticket.updated_at.desc()).limit(25)).all()
        return [public_ticket(t) for t in rows]

    @router.get('/tickets/{identifier}')
    def detail(identifier: int, session: DB, identity: Customer):
        return public_detail(session, owned(session, identity, identifier))

    @router.post('/tickets', status_code=201)
    def submit(body: TicketCreate, session: DB, identity: Customer):
        count = session.exec(select(func.count()).select_from(Ticket).where(Ticket.customer_id == identity.customer_id)).one()
        if count >= 25:
            raise HTTPException(429, 'This support session allows 25 enquiries. Continue an existing enquiry.')
        ticket = Ticket(workspace_id=identity.workspace_id, customer_id=identity.customer_id,
            **body.model_dump(), original_subject=body.subject, original_body=body.body)
        session.add(ticket)
        session.flush()
        session.add(TicketRevision(ticket_id=ticket.id, revision=1, **body.model_dump()))
        session.add(TicketMessage(ticket_id=ticket.id, author='customer', kind='request', body=body.body))
        session.add(AuditEvent(workspace_id=identity.workspace_id, ticket_id=ticket.id, actor='customer', action='enquiry_submitted'))
        session.commit()
        try:
            enqueue(app, 'resolve', ticket.id, identity.workspace_id, identity.workspace_id != 1)
        except HTTPException as error:
            # Admission failures never lose the customer's enquiry.
            if error.status_code == 401:
                raise
            session.expire_all()
            ticket = owned(session, identity, ticket.id)
            ticket.status, ticket.resolution_state, ticket.review_reason = 'open', 'needs_review', 'provider_unavailable'
            ticket.outcome_version += 1
            session.add(ticket)
            session.add(TicketMessage(ticket_id=ticket.id, author='system', kind='handoff', body=REASONS['provider_unavailable']))
            session.commit()
        session.expire_all()
        return public_detail(session, owned(session, identity, ticket.id))

    @router.post('/tickets/{identifier}/followup')
    def followup(identifier: int, body: CustomerFollowup, session: DB, identity: Customer):
        ticket = owned(session, identity, identifier)
        if ticket.outcome_version != body.expected_version:
            raise HTTPException(409, 'This enquiry has changed. Refresh before replying.')
        ticket.status, ticket.resolution_state, ticket.review_reason = 'open', 'needs_review', 'customer_followup'
        ticket.outcome_version += 1
        ticket.draft_run_id = None
        ticket.updated_at = now()
        session.add(ticket)
        session.add(TicketMessage(ticket_id=identifier, author='customer', kind='followup', body=body.body))
        session.add(AuditEvent(workspace_id=identity.workspace_id, ticket_id=identifier,
            actor='customer', action='customer_reopened', detail={'message': body.body}))
        session.commit()
        return public_detail(session, ticket)

    app.include_router(router)
