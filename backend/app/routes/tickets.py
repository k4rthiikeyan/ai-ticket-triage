from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, func
from sqlmodel import select
from ..models import AuditEvent, Category, Decision, Note, Queue, RecommendationRun, Ticket, TicketRevision, now
from ..schemas import DecisionBody, NoteBody, TicketCreate, TicketUpdate
from ..dependencies import DB, authenticated, found
from ..services.records import audit, ticket_data
from ..jobs import enqueue
from ..services.workspaces import workspace_id, state_for, enforce_size


def register(app):
    settings = app.state.settings
    router = APIRouter(prefix="/api", dependencies=[Depends(authenticated)])

    @router.get('/tickets')
    def tickets(session: DB, q: str = '', status: str = '', category_id: int | None = None,
                priority: str = '', queue_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        statement = select(Ticket).where(Ticket.workspace_id == workspace_id(session))
        if q:
            statement = statement.where(or_(Ticket.subject.ilike(f'%{q}%'), Ticket.body.ilike(f'%{q}%'), Ticket.id == (int(q.lstrip('#')) if q.lstrip('#').isdigit() else -1)))
        if status:
            statement = statement.where(Ticket.status == status)
        if category_id:
            statement = statement.where(Ticket.category_id == category_id)
        if priority:
            statement = statement.where(Ticket.priority == priority)
        if queue_id:
            statement = statement.where(Ticket.queue_id == queue_id)
        total = session.exec(select(func.count()).select_from(statement.subquery())).one()
        rows = session.exec(statement.order_by(Ticket.created_at.desc(), Ticket.id.desc()).offset(offset).limit(limit)).all()
        return {'items': [ticket_data(t, session) for t in rows], 'total': total, 'offset': offset, 'limit': limit}


    @router.post('/tickets', status_code=201)
    def add_ticket(body: TicketCreate, session: DB):
        if session.info.get('is_demo'):
            enforce_size(session, Ticket, settings.demo_ticket_limit)
        ticket = Ticket(workspace_id=workspace_id(session), **body.model_dump(), original_subject=body.subject, original_body=body.body)
        session.add(ticket)
        session.flush()
        session.add(TicketRevision(ticket_id=ticket.id, revision=1, **body.model_dump()))
        audit(session, 'ticket_created', {'revision': 1}, ticket.id)
        session.commit()
        session.refresh(ticket)
        return ticket_data(ticket, session)


    @router.get('/tickets/{identifier}')
    def ticket_detail(identifier: int, session: DB):
        ticket = found(session, Ticket, identifier)
        runs = session.exec(select(RecommendationRun).where(RecommendationRun.ticket_id == identifier).order_by(RecommendationRun.created_at.desc())).all()
        state = state_for(session)
        run_data = []
        for run in runs:
            data = run.model_dump(mode='json')
            data['stale'] = run.ticket_revision != ticket.revision or run.taxonomy_version != state.taxonomy_version or (run.method == 'rag' and (run.index_version != state.index_id or state.knowledge_version != state.index_knowledge_version))
            run_data.append(data)
        return {'ticket': ticket_data(ticket, session), 'runs': run_data,
                'notes': session.exec(select(Note).where(Note.ticket_id == identifier).order_by(Note.created_at.desc())).all(),
                'decisions': session.exec(select(Decision).where(Decision.ticket_id == identifier).order_by(Decision.created_at.desc())).all(),
                'revisions': session.exec(select(TicketRevision).where(TicketRevision.ticket_id == identifier).order_by(TicketRevision.revision.desc())).all(),
                'audit': session.exec(select(AuditEvent).where(AuditEvent.ticket_id == identifier).order_by(AuditEvent.created_at.desc())).all()}


    @router.patch('/tickets/{identifier}')
    def update_ticket(identifier: int, body: TicketUpdate, session: DB):
        ticket = found(session, Ticket, identifier)
        if body.expected_revision != ticket.revision:
            raise HTTPException(409, 'Ticket changed. Refresh before saving.')
        before = ticket.model_dump(mode='json')
        text_changed = any(getattr(body, field) is not None and getattr(body, field) != getattr(ticket, field) for field in ['subject', 'body'])
        if text_changed:
            ticket.subject = body.subject if body.subject is not None else ticket.subject
            ticket.body = body.body if body.body is not None else ticket.body
            ticket.revision += 1
            ticket.category_id = ticket.priority = ticket.queue_id = None
            ticket.status = 'new'
            session.add(TicketRevision(ticket_id=ticket.id, revision=ticket.revision, subject=ticket.subject, body=ticket.body))
        if body.status:
            if not ticket.category_id or not ticket.queue_id or not ticket.priority:
                raise HTTPException(409, 'Confirm category, priority, and queue before changing status.')
            ticket.status = body.status
        ticket.updated_at = now()
        session.add(ticket)
        audit(session, 'ticket_updated', {'before': before, 'after': ticket.model_dump(mode='json')}, identifier)
        session.commit()
        session.refresh(ticket)
        return ticket_data(ticket, session)


    @router.post('/tickets/{identifier}/notes', status_code=201)
    def add_note(identifier: int, body: NoteBody, session: DB):
        found(session, Ticket, identifier)
        note = Note(ticket_id=identifier, body=body.body)
        session.add(note)
        audit(session, 'note_added', {'body': body.body}, identifier)
        session.commit()
        session.refresh(note)
        return note


    @router.post('/tickets/{identifier}/triage', status_code=202)
    def triage(identifier: int, session: DB, method: Literal['rag', 'rules'] = 'rag'):
        found(session, Ticket, identifier)
        return enqueue(app, method, identifier, workspace_id(session), session.info.get('is_demo', False))


    @router.post('/tickets/{identifier}/decisions', status_code=201)
    def decision(identifier: int, body: DecisionBody, session: DB):
        ticket = found(session, Ticket, identifier)
        if body.expected_revision != ticket.revision:
            raise HTTPException(409, 'Ticket changed. Refresh before confirming.')
        category = found(session, Category, body.category_id)
        queue = found(session, Queue, body.queue_id)
        if not category.active or not queue.active:
            raise HTTPException(422, 'Final decisions must use an active category and queue.')
        action = 'manual'
        if body.recommendation_id:
            run = found(session, RecommendationRun, body.recommendation_id)
            state = state_for(session)
            if run.ticket_id != identifier or run.ticket_revision != ticket.revision or run.taxonomy_version != state.taxonomy_version:
                raise HTTPException(409, 'This recommendation is stale or belongs to another ticket. Run triage again or make a manual decision.')
            if run.method == 'rag' and (run.index_version != state.index_id or state.knowledge_version != state.index_knowledge_version):
                raise HTTPException(409, 'Knowledge changed after this recommendation. Rebuild and run triage again.')
            if run.outcome != 'suggested':
                raise HTTPException(422, 'This run has no suggestion to accept. Make a manual decision.')
            final = {'category_id': body.category_id, 'priority': body.priority, 'queue_id': body.queue_id}
            action = 'accepted' if run.payload['suggestions'] == final else 'overridden'
        record = Decision(ticket_id=identifier, ticket_revision=ticket.revision, recommendation_id=body.recommendation_id,
                          category_id=body.category_id, priority=body.priority, queue_id=body.queue_id, action=action, note=body.note)
        before = {'category_id': ticket.category_id, 'priority': ticket.priority, 'queue_id': ticket.queue_id, 'status': ticket.status}
        ticket.category_id, ticket.priority, ticket.queue_id = body.category_id, body.priority, body.queue_id
        if ticket.status == 'new':
            ticket.status = 'open'
        ticket.updated_at = now()
        session.add(ticket)
        session.add(record)
        audit(session, 'decision_' + action, {'before': before, 'after': record.model_dump(mode='json')}, identifier)
        session.commit()
        session.refresh(record)
        return record


    @router.get('/dashboard')
    def dashboard(session: DB):
        all_tickets = session.exec(select(Ticket).where(Ticket.workspace_id == workspace_id(session))).all()
        categories = session.exec(select(Category)).all()
        queues = session.exec(select(Queue)).all()
        return {'total': len(all_tickets), 'status': {s: sum(t.status == s for t in all_tickets) for s in ['new', 'open', 'resolved']},
                'categories': [{'name': c.name, 'count': sum(t.category_id == c.id for t in all_tickets)} for c in categories]
                              + [{'name': 'Untriaged', 'count': sum(t.category_id is None for t in all_tickets)}],
                'priorities': [{'name': p, 'count': sum(t.priority == p for t in all_tickets)} for p in ['urgent', 'high', 'normal', 'low']]
                              + [{'name': 'Untriaged', 'count': sum(t.priority is None for t in all_tickets)}],
                'queues': [{'name': q.name, 'count': sum(t.queue_id == q.id and t.status != 'resolved' for t in all_tickets)} for q in queues],
                'recent': [ticket_data(t, session) for t in sorted(all_tickets, key=lambda t: t.updated_at, reverse=True)[:5]]}


    app.include_router(router)
