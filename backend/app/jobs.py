import logging
import time
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlmodel import Session, select
from .models import AppState, Article, Category, Job, RecommendationRun, Ticket, AuditEvent, now
from .rag import run_rag, run_rules

logger = logging.getLogger(__name__)


def readable_error(error):
    import httpx
    from pydantic import ValidationError
    if isinstance(error, (ConnectionError, httpx.ConnectError)):
        return 'Cannot reach OpenRouter. Check the server network connection and retry. Rules comparison remains available.'
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return 'OpenRouter timed out. Retry or increase INFERENCE_TIMEOUT; rules comparison remains available.'
    if isinstance(error, ValidationError):
        return 'The model returned invalid structured output. Retry or record a manual decision.'
    if isinstance(error, ValueError):
        return str(error)[:600]
    logger.exception('Background operation failed')
    return 'The operation failed. Check the server log and retry.'


def enqueue(app, kind: str, ticket_id=None):
    with app.state.job_lock:
        if app.state.busy:
            raise HTTPException(409, 'Another inference or index rebuild is running. Wait for it to finish.')
        with Session(app.state.engine) as session:
            # A row lock serializes admission across Vercel instances sharing Postgres.
            state = session.exec(select(AppState).where(AppState.id == 1).with_for_update()).one()
            cutoff = now() - timedelta(seconds=app.state.settings.job_timeout + app.state.settings.inference_timeout + 30)
            active = session.exec(select(Job).where(Job.status.in_(['queued', 'running']))).all()
            for prior in active:
                if prior.created_at >= cutoff:
                    raise HTTPException(409, 'Another triage or index rebuild is running. Wait for it to finish.')
                prior.status = 'failed'
                prior.error = 'This operation was interrupted or timed out. Retry explicitly.'
                prior.finished_at = now()
                session.add(prior)
            if kind == 'rag' and (not state.index_id or state.knowledge_version != state.index_knowledge_version or state.embedding_model != app.state.settings.embedding_model):
                raise HTTPException(409, 'The knowledge index is missing or stale. Rebuild it in Knowledge base before running RAG.')
            ticket = session.get(Ticket, ticket_id) if ticket_id else None
            if ticket_id and ticket is None:
                raise HTTPException(404, 'Ticket not found')
            snapshot = {
                'ticket': ticket.model_copy(deep=True) if ticket else None,
                'categories': [c.model_copy(deep=True) for c in session.exec(select(Category).where(Category.active == True)).all()],
                'state': state.model_copy(deep=True),
                'articles': [a.model_copy(deep=True) for a in session.exec(select(Article).where(Article.active == True)).all()] if kind == 'reindex' else [],
            }
            if kind == 'reindex' and not any(a.is_policy for a in snapshot['articles']):
                raise HTTPException(409, 'Add an article marked as an urgency policy before rebuilding the index.')
            if kind == 'reindex' and not any(not a.is_policy for a in snapshot['articles']):
                raise HTTPException(409, 'Add at least one support article before rebuilding the index.')
            if kind == 'rag' and not snapshot['categories']:
                raise HTTPException(409, 'Add an active category and queue in Settings before running triage.')
            job = Job(id=uuid4().hex, kind=kind, ticket_id=ticket_id)
            session.add(job)
            session.commit()
            session.refresh(job)
            result = job.model_dump(mode='json')
        app.state.busy = True
    # Complete work inside the request: serverless instances can stop after a response.
    execute(app, result['id'], snapshot)
    with Session(app.state.engine) as session:
        return session.get(Job, result['id']).model_dump(mode='json')


def execute(app, job_id, snapshot):
    engine = app.state.engine
    ticket = snapshot['ticket']
    state = snapshot['state']
    result_id = None
    deadline = time.monotonic() + app.state.settings.job_timeout

    def progress(message):
        if time.monotonic() > deadline:
            raise TimeoutError('Operation exceeded the prototype request time budget.')
        with Session(engine) as session:
            job = session.get(Job, job_id)
            job.status = 'running'
            job.progress = message
            session.add(job)
            session.commit()

    try:
        progress('Starting operation')
        with Session(engine) as session:
            kind = session.get(Job, job_id).kind
        if kind == 'reindex':
            index_id, count = app.state.store.build(snapshot['articles'], app.state.gateway, progress)
            with Session(engine) as session:
                current = session.get(AppState, 1)
                if current.knowledge_version != state.knowledge_version:
                    raise ValueError('Knowledge changed while indexing. The prior index was preserved; rebuild again.')
                current.index_id = index_id
                current.index_knowledge_version = state.knowledge_version
                current.embedding_model = app.state.settings.embedding_model
                session.add(current)
                session.add(AuditEvent(action='index_activated', detail={'index_id': index_id, 'chunks': count, 'knowledge_version': state.knowledge_version}))
                job = session.get(Job, job_id)
                job.result = {'index_id': index_id, 'chunks': count}
                job.status = 'succeeded'
                job.progress = f'Indexed {count} chunks successfully'
                job.finished_at = now()
                session.add(job)
                session.commit()
        else:
            payload = run_rules(ticket, snapshot['categories']) if kind == 'rules' else run_rag(
                ticket, snapshot['categories'], state, app.state.gateway, app.state.store, app.state.settings, progress)
            result_id = uuid4().hex
            with Session(engine) as session:
                session.add(RecommendationRun(id=result_id, ticket_id=ticket.id, ticket_revision=ticket.revision,
                    taxonomy_version=state.taxonomy_version, index_version=state.index_id if kind == 'rag' else None,
                    method=kind, model=app.state.settings.generation_model if kind == 'rag' else 'deterministic-keywords-v1',
                    outcome=payload['outcome'], payload=payload))
                session.add(AuditEvent(ticket_id=ticket.id, action='triage_completed', detail={'method': kind, 'outcome': payload['outcome'], 'recommendation_id': result_id}))
                job = session.get(Job, job_id)
                job.result = {'recommendation_id': result_id}
                job.status = 'needs_review' if payload['outcome'] == 'needs_review' else 'succeeded'
                job.progress = 'Human confirmation required' if payload['outcome'] == 'suggested' else 'Manual review required'
                job.finished_at = now()
                session.add(job)
                session.commit()
    except Exception as error:
        message = readable_error(error)
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if ticket:
                result_id = uuid4().hex
                session.add(RecommendationRun(id=result_id, ticket_id=ticket.id, ticket_revision=ticket.revision,
                    taxonomy_version=state.taxonomy_version, index_version=state.index_id if job.kind == 'rag' else None,
                    method=job.kind, model=app.state.settings.generation_model if job.kind == 'rag' else 'deterministic-keywords-v1',
                    outcome='failed', payload={'outcome': 'failed', 'suggestions': None, 'error': message, 'citations': [], 'retrieved': [], 'sources': [], 'scores': {}, 'rationales': {'review': message}}))
                job.result = {'recommendation_id': result_id}
            job.status = 'failed'
            job.error = message
            job.progress = 'Operation failed; retry is available'
            job.finished_at = now()
            session.add(job)
            session.add(AuditEvent(ticket_id=ticket.id if ticket else None, action='job_failed', detail={'job_id': job_id, 'error': message}))
            session.commit()
    finally:
        with app.state.job_lock:
            app.state.busy = False
