from datetime import timedelta
from typing import Literal
import json
from fastapi import APIRouter, Depends
from fastapi.openapi.docs import get_swagger_ui_html
from sqlmodel import select
from ..models import Job, now
from ..dependencies import DB, authenticated, administrator, found
from ..jobs import readable_error
from ..services.workspaces import workspace_id, state_for
from ..services.usage import BudgetedGateway, used


def register(app):
    settings = app.state.settings
    router = APIRouter(prefix="/api", dependencies=[Depends(authenticated)])

    @router.get('/docs', include_in_schema=False)
    def docs():
        return get_swagger_ui_html(openapi_url='/api/openapi.json', title='Triage Desk API')


    @router.get('/openapi.json', include_in_schema=False)
    def openapi():
        return app.openapi()


    @router.get('/system')
    def system(session: DB):
        state = state_for(session)
        ready = bool(state.index_id and state.index_knowledge_version == state.knowledge_version and state.embedding_model == settings.embedding_model)
        provider = app.state.gateway.status()
        cutoff = now() - timedelta(seconds=settings.job_timeout + settings.inference_timeout + 30)
        return {'index_ready': ready, 'index_id': state.index_id, 'knowledge_version': state.knowledge_version,
                'indexed_version': state.index_knowledge_version, 'generation_model': settings.generation_model,
                'embedding_model': settings.embedding_model, 'provider': provider,
                'demo_limits': {'ai_requests_per_day': settings.demo_ai_daily_limit,
                                'ai_remaining_today': max(0, min(settings.demo_ai_daily_limit - used(session, f'ai:workspace:{workspace_id(session)}'),
                                                               settings.ai_daily_limit - used(session, 'ai:global:day'))),
                                'tickets': settings.demo_ticket_limit,
                                'articles': settings.demo_article_limit, 'idle_minutes': settings.demo_idle_minutes},
                'busy': bool(session.exec(select(Job).where(Job.workspace_id == workspace_id(session), Job.status.in_(['queued', 'running']), Job.created_at >= cutoff)).first()),
                'jobs': session.exec(select(Job).where(Job.workspace_id == workspace_id(session)).order_by(Job.created_at.desc()).limit(5)).all()}


    @router.post('/system/check-provider', dependencies=[Depends(administrator)])
    def check_provider(kind: Literal['embeddings', 'llm']):
        result = {'kind': kind, 'model': settings.embedding_model if kind == 'embeddings' else settings.generation_model,
                  'free_only': True}
        try:
            if kind == 'embeddings':
                vectors = BudgetedGateway(app).embed(['Connection check.'])
                result['dimensions'] = len(vectors[0])
            else:
                schema = {'type': 'object', 'properties': {'connected': {'type': 'boolean', 'const': True}},
                          'required': ['connected'], 'additionalProperties': False}
                content = BudgetedGateway(app).generate([
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


    app.include_router(router)
