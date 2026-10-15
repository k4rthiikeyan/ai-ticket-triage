import hashlib
import secrets
from typing import Annotated
from fastapi import Depends, HTTPException, Request, Header
from sqlmodel import Session
from .config import DEMO_USERNAME
from .models import Admin, LoginSession, RecommendationRun, Ticket, Workspace, now
from .services.workspaces import workspace_id
from .services.usage import consume
def database(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


DB = Annotated[Session, Depends(database)]

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticated(request: Request, session: DB, csrf_header: Annotated[str | None, Header(alias='X-CSRF-Token')] = None):
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
    workspace = session.get(Workspace, login.workspace_id)
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


