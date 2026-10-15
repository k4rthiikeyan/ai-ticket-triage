import hashlib
import secrets
from datetime import timedelta
from typing import Annotated
from fastapi import Depends, HTTPException, Request, Response, Header
from sqlmodel import Session, select
from sqlalchemy.orm.exc import StaleDataError
from .config import DEMO_USERNAME
from .models import Admin, LoginSession, RecommendationRun, Ticket, Workspace, now
from .services.workspaces import workspace_id, cleanup_expired
from .services.usage import consume
def database(request: Request):
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        cleanup_expired(session)
        session.commit()
        yield session


DB = Annotated[Session, Depends(database)]

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticated(request: Request, response: Response, session: DB, csrf_header: Annotated[str | None, Header(alias='X-CSRF-Token')] = None):
    token = request.cookies.get('triage_session')
    login = session.get(LoginSession, token_hash(token)) if token else None
    if not login or login.expires_at <= now():
        raise HTTPException(401, 'Please sign in to continue.')
    admin = session.get(Admin, login.admin_id)
    if not admin or (admin.username == DEMO_USERNAME and not request.app.state.settings.public_demo_enabled):
        raise HTTPException(401, 'Please sign in to continue.')
    if admin.username == DEMO_USERNAME and login.workspace_id == 1:
        # Reject legacy tokens even if an older deployment issued one during rollout.
        raise HTTPException(401, 'Sign in again to start your isolated demo workspace.')
    workspace = (session.exec(select(Workspace).where(Workspace.id == login.workspace_id).with_for_update()).first()
                 if admin.username == DEMO_USERNAME else session.get(Workspace, login.workspace_id))
    if not workspace or (workspace.expires_at and workspace.expires_at <= now()):
        raise HTTPException(401, 'Your demo workspace expired. Sign in to start a fresh workspace.')
    session.info.update(workspace_id=login.workspace_id, is_demo=admin.username == DEMO_USERNAME)
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        csrf = csrf_header or ''
        if not secrets.compare_digest(csrf, login.csrf_token):
            raise HTTPException(403, 'Invalid CSRF token. Refresh the page and retry.')
        if admin.username == DEMO_USERNAME:
            # Protect storage as well as provider quota. Reads and logout remain available.
            if not request.url.path.endswith('/auth/logout'):
                consume(session, 'demo:writes:global', 300, 86400)
                consume(session, f'demo:writes:{login.workspace_id}', 80, 3600)
                session.commit()
    if admin.username == DEMO_USERNAME:
        deadline = now() + timedelta(minutes=request.app.state.settings.demo_idle_minutes)
        # Replace old eight-hour sessions as well as extending active new ones.
        login.expires_at = workspace.expires_at = deadline
        session.add(login)
        session.add(workspace)
        try:
            session.commit()
        except StaleDataError as error:
            session.rollback()
            raise HTTPException(401, 'Your demo session ended. Sign in again to continue.') from error
        response.set_cookie('triage_session', token, httponly=True, secure=request.app.state.settings.cookie_secure,
                            samesite='strict', path='/api')
    return login


def administrator(session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
    if session.get(Admin, login.admin_id).username == DEMO_USERNAME:
        raise HTTPException(403, 'This setting is managed by the workspace administrator. Demo users can try tickets and knowledge.')


def found(session, model, identifier):
    item = session.get(model, identifier)
    allowed = item is not None
    if allowed and hasattr(item, 'workspace_id'):
        allowed = item.workspace_id == workspace_id(session)
    if allowed and isinstance(item, RecommendationRun):
        allowed = session.get(Ticket, item.ticket_id).workspace_id == workspace_id(session)
    if not allowed:
        raise HTTPException(404, f'{model.__name__} not found')
    return item


