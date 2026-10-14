import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, Query, Header
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pwdlib import PasswordHash
from sqlalchemy import or_, func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from .config import Settings, get_settings, DEMO_USERNAME, DEMO_PASSWORD
from .db import make_engine, migrate
from .models import *
from .schemas import *
from .seed import seed
from .rag import OpenRouterGateway, VectorStore, embed_query
from .jobs import enqueue, readable_error


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
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        csrf = csrf_header or ''
        if not secrets.compare_digest(csrf, login.csrf_token):
            raise HTTPException(403, 'Invalid CSRF token. Refresh the page and retry.')
    return login


def administrator(session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
    if session.get(Admin, login.admin_id).username == DEMO_USERNAME:
        raise HTTPException(403, 'This setting is managed by the workspace administrator. Demo users can try tickets and knowledge.')


def found(session, model, identifier):
    item = session.get(model, identifier)
    if item is None:
        raise HTTPException(404, f'{model.__name__} not found')
    return item


def changed_knowledge(session, taxonomy=False):
    values = {'knowledge_version': AppState.knowledge_version + 1}
    if taxonomy:
        values['taxonomy_version'] = AppState.taxonomy_version + 1
    session.exec(update(AppState).where(AppState.id == 1).values(**values))


def audit(session, action, detail, ticket_id=None):
    session.add(AuditEvent(ticket_id=ticket_id, action=action, detail=detail))


def ticket_data(ticket, session):
    data = ticket.model_dump(mode='json')
    category = session.get(Category, ticket.category_id) if ticket.category_id else None
    queue = session.get(Queue, ticket.queue_id) if ticket.queue_id else None
    data.update(category_name=category.name if category else None, queue_name=queue.name if queue else None)
    return data


def create_app(settings: Settings | None = None, gateway=None, store=None, frontend_dir=None):
    settings = settings or get_settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        if settings.auto_migrate:
            migrate(engine)
        seed(engine, settings)
        with Session(engine) as session:
            cutoff = now() - timedelta(seconds=settings.job_timeout + settings.inference_timeout + 30)
            for job in session.exec(select(Job).where(Job.status.in_(['queued', 'running']), Job.created_at < cutoff)).all():
                job.status = 'failed'
                job.error = 'This operation exceeded its time limit or was interrupted. Retry explicitly.'
                job.progress = 'Interrupted by restart'
                job.finished_at = now()
                session.add(job)
            session.commit()
        yield
        if hasattr(app.state.gateway, 'close'):
            app.state.gateway.close()
        engine.dispose()

    app = FastAPI(title='Triage Desk API', version='1.0.0', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = settings
    app.state.gateway = gateway or OpenRouterGateway(settings)
    app.state.store = store or VectorStore(engine, settings.max_index_chunks)
    app.state.busy = False
    app.state.job_lock = Lock()

    @app.middleware('http')
    async def origin_and_headers(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ['GET', 'HEAD', 'OPTIONS'] and origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Cross-origin writes are not allowed.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(IntegrityError)
    async def duplicate_error(request, error):
        return JSONResponse({'detail': 'That name already exists or a referenced record is invalid.'}, status_code=409)

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/auth/demo')
    def demo_access():
        if not settings.public_demo_enabled:
            return {'enabled': False}
        return {'enabled': True, 'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}

    @app.post('/api/auth/login')
    def login(body: LoginBody, request: Request, response: Response, session: DB):
        admin = session.exec(select(Admin).where(Admin.username == body.username)).first()
        if (not admin or (admin.username == DEMO_USERNAME and not settings.public_demo_enabled)
                or not PasswordHash.recommended().verify(body.password, admin.password_hash)):
            raise HTTPException(401, 'Username or password is incorrect.')
        old_token = request.cookies.get('triage_session')
        old_session = session.get(LoginSession, token_hash(old_token)) if old_token else None
        if old_session:
            session.delete(old_session)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        session.add(LoginSession(token_hash=token_hash(token), admin_id=admin.id, csrf_token=csrf,
                                 expires_at=now() + timedelta(hours=settings.session_hours)))
        session.commit()
        response.set_cookie('triage_session', token, httponly=True, secure=settings.cookie_secure,
                            samesite='strict', path='/api', max_age=settings.session_hours * 3600)
        return {'username': admin.username, 'csrf_token': csrf, 'is_demo': admin.username == DEMO_USERNAME}

    router = APIRouter(prefix='/api', dependencies=[Depends(authenticated)])

    @router.get('/auth/me')
    def me(session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
        username = session.get(Admin, login.admin_id).username
        return {'username': username, 'csrf_token': login.csrf_token, 'is_demo': username == DEMO_USERNAME}

    @router.post('/auth/logout')
    def logout(response: Response, session: DB, login: Annotated[LoginSession, Depends(authenticated)]):
        session.delete(login)
        session.commit()
        response.delete_cookie('triage_session', path='/api')
        return {'ok': True}

    @router.get('/docs', include_in_schema=False)
    def docs():
        return get_swagger_ui_html(openapi_url='/api/openapi.json', title='Triage Desk API')

    @router.get('/openapi.json', include_in_schema=False)
    def openapi():
        return app.openapi()

    @router.get('/system')
    def system(session: DB):
        state = session.get(AppState, 1)
        ready = bool(state.index_id and state.index_knowledge_version == state.knowledge_version and state.embedding_model == settings.embedding_model)
        provider = app.state.gateway.status()
        cutoff = now() - timedelta(seconds=settings.job_timeout + settings.inference_timeout + 30)
        return {'index_ready': ready, 'index_id': state.index_id, 'knowledge_version': state.knowledge_version,
                'indexed_version': state.index_knowledge_version, 'generation_model': settings.generation_model,
                'embedding_model': settings.embedding_model, 'provider': provider,
                'busy': bool(session.exec(select(Job).where(Job.status.in_(['queued', 'running']), Job.created_at >= cutoff)).first()),
                'jobs': session.exec(select(Job).order_by(Job.created_at.desc()).limit(5)).all()}

    @router.post('/system/check-provider', dependencies=[Depends(administrator)])
    def check_provider(kind: Literal['embeddings', 'llm']):
        result = {'kind': kind, 'model': settings.embedding_model if kind == 'embeddings' else settings.generation_model,
                  'free_only': True}
        try:
            if kind == 'embeddings':
                vectors = app.state.gateway.embed(['Connection check.'])
                result['dimensions'] = len(vectors[0])
            else:
                schema = {'type': 'object', 'properties': {'connected': {'type': 'boolean', 'const': True}},
                          'required': ['connected'], 'additionalProperties': False}
                content = app.state.gateway.generate([
                    {'role': 'user', 'content': 'Connection check only. Return a JSON object with connected set to true.'}
                ], schema)
                try:
                    valid = json.loads(content) == {'connected': True}
                except (ValueError, TypeError):
                    valid = False
                if not valid:
                    raise ValueError('OpenRouter returned an invalid connection check response.')
            return {**result, 'available': True}
        except Exception as error:
            return {**result, 'available': False, 'message': readable_error(error)}

    @router.get('/taxonomy')
    def taxonomy(session: DB):
        return {'categories': session.exec(select(Category).order_by(Category.id)).all(),
                'queues': session.exec(select(Queue).order_by(Queue.id)).all()}

    @router.post('/queues', status_code=201, dependencies=[Depends(administrator)])
    def add_queue(body: QueueBody, session: DB):
        queue = Queue(**body.model_dump())
        session.add(queue)
        changed_knowledge(session, True)
        audit(session, 'queue_created', body.model_dump())
        session.commit()
        session.refresh(queue)
        return queue

    @router.patch('/queues/{identifier}', dependencies=[Depends(administrator)])
    def update_queue(identifier: int, body: QueueBody, session: DB):
        queue = found(session, Queue, identifier)
        if not body.active and session.exec(select(Category).where(Category.active == True, Category.queue_id == identifier)).first():
            raise HTTPException(409, 'Reassign or archive active categories before archiving their queue.')
        queue.sqlmodel_update(body.model_dump())
        session.add(queue)
        changed_knowledge(session, True)
        audit(session, 'queue_updated', {'id': identifier, **body.model_dump()})
        session.commit()
        session.refresh(queue)
        return queue

    @router.post('/categories', status_code=201, dependencies=[Depends(administrator)])
    def add_category(body: CategoryBody, session: DB):
        queue = found(session, Queue, body.queue_id)
        if body.active and not queue.active:
            raise HTTPException(422, 'Choose an active queue.')
        category = Category(slug='custom-' + uuid4().hex[:12], **body.model_dump())
        session.add(category)
        changed_knowledge(session, True)
        audit(session, 'category_created', body.model_dump())
        session.commit()
        session.refresh(category)
        return category

    @router.patch('/categories/{identifier}', dependencies=[Depends(administrator)])
    def update_category(identifier: int, body: CategoryBody, session: DB):
        category = found(session, Category, identifier)
        queue = found(session, Queue, body.queue_id)
        if body.active and not queue.active:
            raise HTTPException(422, 'Choose an active queue.')
        category.sqlmodel_update(body.model_dump())
        session.add(category)
        changed_knowledge(session, True)
        audit(session, 'category_updated', {'id': identifier, **body.model_dump()})
        session.commit()
        session.refresh(category)
        return category

    @router.get('/tickets')
    def tickets(session: DB, q: str = '', status: str = '', category_id: int | None = None,
                priority: str = '', queue_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        statement = select(Ticket)
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
        ticket = Ticket(**body.model_dump(), original_subject=body.subject, original_body=body.body)
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
        state = session.get(AppState, 1)
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
    def triage(identifier: int, method: Literal['rag', 'rules'] = 'rag'):
        return enqueue(app, method, identifier)

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
            state = session.get(AppState, 1)
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

    @router.get('/jobs/{identifier}')
    def job_detail(identifier: str, session: DB):
        job = found(session, Job, identifier)
        cutoff = now() - timedelta(seconds=settings.job_timeout + settings.inference_timeout + 30)
        if job.status in ['queued', 'running'] and job.created_at < cutoff:
            job.status = 'failed'
            job.error = 'This operation was interrupted or timed out. Retry explicitly.'
            job.finished_at = now()
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    @router.get('/dashboard')
    def dashboard(session: DB):
        all_tickets = session.exec(select(Ticket)).all()
        categories = session.exec(select(Category)).all()
        queues = session.exec(select(Queue)).all()
        return {'total': len(all_tickets), 'status': {s: sum(t.status == s for t in all_tickets) for s in ['new', 'open', 'resolved']},
                'categories': [{'name': c.name, 'count': sum(t.category_id == c.id for t in all_tickets)} for c in categories]
                              + [{'name': 'Untriaged', 'count': sum(t.category_id is None for t in all_tickets)}],
                'priorities': [{'name': p, 'count': sum(t.priority == p for t in all_tickets)} for p in ['urgent', 'high', 'normal', 'low']]
                              + [{'name': 'Untriaged', 'count': sum(t.priority is None for t in all_tickets)}],
                'queues': [{'name': q.name, 'count': sum(t.queue_id == q.id and t.status != 'resolved' for t in all_tickets)} for q in queues],
                'recent': [ticket_data(t, session) for t in sorted(all_tickets, key=lambda t: t.updated_at, reverse=True)[:5]]}

    @router.get('/articles')
    def articles(session: DB):
        return session.exec(select(Article).order_by(Article.is_policy.desc(), Article.title)).all()

    @router.get('/articles/{identifier}/revisions')
    def article_history(identifier: str, session: DB):
        found(session, Article, identifier)
        return session.exec(select(ArticleRevision).where(ArticleRevision.article_id == identifier).order_by(ArticleRevision.revision.desc())).all()

    @router.post('/articles', status_code=201)
    def add_article(body: ArticleBody, session: DB):
        article = Article(id='article-' + uuid4().hex[:12], **body.model_dump())
        session.add(article)
        session.flush()
        session.add(ArticleRevision(article_id=article.id, revision=1, title=body.title, body=body.body, active=True))
        changed_knowledge(session)
        audit(session, 'article_created', {'article_id': article.id})
        session.commit()
        session.refresh(article)
        return article

    @router.patch('/articles/{identifier}')
    def update_article(identifier: str, body: ArticleUpdate, session: DB):
        article = found(session, Article, identifier)
        if body.expected_revision != article.revision:
            raise HTTPException(409, 'Article changed. Refresh before saving.')
        if article.is_policy and not body.active:
            raise HTTPException(409, 'The shared urgency policy cannot be archived.')
        article.title, article.body, article.active = body.title, body.body, body.active
        article.revision += 1
        article.updated_at = now()
        session.add(article)
        session.add(ArticleRevision(article_id=article.id, revision=article.revision, title=article.title, body=article.body, active=article.active))
        changed_knowledge(session)
        audit(session, 'article_updated', {'article_id': identifier, 'revision': article.revision, 'active': article.active})
        session.commit()
        session.refresh(article)
        return article

    @router.post('/knowledge/reindex', status_code=202)
    def reindex():
        return enqueue(app, 'reindex')

    @router.post('/knowledge/search')
    def search_knowledge(body: KnowledgeSearch, session: DB):
        state = session.get(AppState, 1)
        if not state.index_id or state.knowledge_version != state.index_knowledge_version or state.embedding_model != settings.embedding_model:
            raise HTTPException(409, 'Add your knowledge and rebuild the index before searching.')
        try:
            vector = embed_query(body.query, app.state.gateway)
            results, _ = app.state.store.retrieve(state.index_id, vector, top_k=body.limit)
            return {'items': [source for source in results if source['similarity'] >= settings.retrieval_threshold],
                    'index_id': state.index_id, 'embedding_model': settings.embedding_model}
        except Exception as error:
            raise HTTPException(502, readable_error(error)) from error

    app.include_router(router)
    dist = Path(frontend_dir) if frontend_dir is not None else Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    if (dist / 'index.html').is_file() and (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')
        index_file = dist / 'index.html'
        index_etag = '"' + hashlib.sha256(index_file.read_bytes()).hexdigest() + '"'

        @app.get('/{path:path}', include_in_schema=False)
        def frontend(path: str):
            if path.startswith('api/'):
                raise HTTPException(404, 'Endpoint not found')
            return FileResponse(index_file, headers={'Cache-Control': 'no-store',
                'Vercel-CDN-Cache-Control': 'no-store', 'ETag': index_etag})
    return app


app = create_app()
