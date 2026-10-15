import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from .config import Settings, get_settings
from .db import make_engine, migrate
from .seed import seed
from .rag import OpenRouterGateway, VectorStore
from .routes import auth, system, taxonomy, tickets, knowledge, portal
from .services.workspaces import shorten_legacy_sessions, cleanup_expired
from .jobs import recover_overdue


def create_app(settings: Settings | None = None, gateway=None, store=None, frontend_dir=None):
    settings = settings or get_settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        if settings.auto_migrate:
            migrate(engine)
        seed(engine, settings)
        with Session(engine) as session:
            shorten_legacy_sessions(session, settings)
            cleanup_expired(session)
            recover_overdue(session, settings)
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


    for feature in (auth, system, taxonomy, tickets, knowledge, portal):
        feature.register(app)
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
