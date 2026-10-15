from datetime import timedelta
from typing import Annotated
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlmodel import select
from ..config import DEMO_USERNAME, DEMO_PASSWORD
from ..models import Admin, LoginSession, Workspace, now
from ..schemas import LoginBody
from ..dependencies import DB, authenticated, token_hash
from ..services.workspaces import create_demo_workspace, delete_workspace
from ..services.usage import consume


def register(app):
    settings = app.state.settings
    router = APIRouter(prefix="/api", dependencies=[Depends(authenticated)])

    @app.get('/api/auth/demo')
    def demo_access():
        if not settings.public_demo_enabled:
            return {'enabled': False}
        return {'enabled': True, 'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}


    @app.post('/api/auth/login')
    def login(body: LoginBody, request: Request, response: Response, session: DB):
        consume(session, 'login:global', 120, 3600)
        consume(session, 'login:client:' + (request.client.host if request.client else 'unknown'), 30, 3600)
        session.commit()
        admin = session.exec(select(Admin).where(Admin.username == body.username)).first()
        if (not admin or (admin.username == DEMO_USERNAME and not settings.public_demo_enabled)
                or not PasswordHash.recommended().verify(body.password, admin.password_hash)):
            raise HTTPException(401, 'Username or password is incorrect.')
        old_token = request.cookies.get('triage_session')
        old_session = session.get(LoginSession, token_hash(old_token)) if old_token else None
        if old_session:
            session.delete(old_session)
            session.flush()
        workspace = 1
        if admin.username == DEMO_USERNAME:
            prior = session.get(Workspace, old_session.workspace_id) if old_session and old_session.admin_id == admin.id else None
            if prior and prior.expires_at and prior.expires_at > now() and old_session.expires_at > now():
                workspace = prior.id
            else:
                consume(session, 'demo:new:global', 40, 86400)
                workspace = create_demo_workspace(session, settings, body.starter_examples)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        is_demo = admin.username == DEMO_USERNAME
        expires_at = now() + (timedelta(minutes=settings.demo_idle_minutes) if is_demo else timedelta(hours=settings.session_hours))
        session.add(LoginSession(token_hash=token_hash(token), admin_id=admin.id, csrf_token=csrf,
                                 workspace_id=workspace,
                                 expires_at=expires_at))
        session.commit()
        response.set_cookie('triage_session', token, httponly=True, secure=settings.cookie_secure,
                            samesite='strict', path='/api', max_age=None if is_demo else settings.session_hours * 3600)
        return {'username': admin.username, 'csrf_token': csrf, 'is_demo': admin.username == DEMO_USERNAME}


    @router.get('/auth/me')
    def me(session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
        username = session.get(Admin, login.admin_id).username
        return {'username': username, 'csrf_token': login.csrf_token, 'is_demo': username == DEMO_USERNAME}


    @router.post('/auth/logout')
    def logout(response: Response, session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
        if session.info.get('is_demo'):
            delete_workspace(session, login.workspace_id)
        else:
            session.delete(login)
        session.commit()
        response.delete_cookie('triage_session', path='/api')
        return {'ok': True}


    app.include_router(router)
