import logging
import time
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import delete
from .models import AppState, Article, Category, Job, RecommendationRun, Ticket, AuditEvent, KnowledgeChunk, Workspace, TicketMessage, Decision, now
from .rag import run_rag, run_rules
from .services.usage import BudgetedGateway
from .services.workspaces import cleanup_expired
from .services.resolution import run_resolution, needs_review, risk_reason, REASONS

logger = logging.getLogger(__name__)


def recover_interrupted(session, job):
    """A stopped request must not leave a customer waiting in processing forever."""
    if job.kind not in ['resolve', 'revise'] or not job.ticket_id:
        return
    ticket = session.exec(select(Ticket).where(Ticket.id == job.ticket_id).with_for_update()).first()
    if (ticket and ticket.resolution_state == 'processing'
            and ticket.outcome_version == job.result.get('outcome_version')):
        ticket.status, ticket.resolution_state, ticket.review_reason = 'open', 'needs_review', 'provider_unavailable'
        ticket.outcome_version += 1
        ticket.updated_at = now()
        session.add(ticket)
        session.add(TicketMessage(ticket_id=ticket.id, author='system', kind='handoff',
            body='Your request was interrupted. It is saved for our support team to review.'))


def recover_overdue(session, settings):
    """Recover bounded, overdue work on warm instances as well as at startup."""
    cutoff = now() - timedelta(seconds=settings.job_timeout + settings.inference_timeout + 30)
    jobs = session.exec(select(Job).where(Job.status.in_(['queued', 'running']), Job.created_at < cutoff)
                        .with_for_update(skip_locked=True).limit(10)).all()
    for job in jobs:
        if job.kind in ['resolve', 'revise'] and job.ticket_id:
            # Never wait on a publishing transaction while holding its job lock.
            ticket = session.exec(select(Ticket).where(Ticket.id == job.ticket_id)
                                  .with_for_update(skip_locked=True)).first()
            if ticket is None:
                continue
        job.status = 'failed'
        job.error = 'This operation exceeded its time limit or was interrupted. Retry explicitly.'
        job.progress = 'Interrupted request recovered'
        job.finished_at = now()
        session.add(job)
        recover_interrupted(session, job)


def readable_error(error):
    import httpx
    from pydantic import ValidationError
    if isinstance(error, HTTPException):
        return str(error.detail)
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


def enqueue(app, kind: str, ticket_id=None, workspace=1, is_demo=False):
    with app.state.job_lock:
        if app.state.busy:
            raise HTTPException(409, 'Another inference or index rebuild is running. Wait for it to finish.')
        with Session(app.state.engine) as session:
            # A row lock serializes admission across Vercel instances sharing Postgres.
            session.exec(select(AppState).where(AppState.id == 1).with_for_update()).one()
            member = session.exec(select(Workspace).where(Workspace.id == workspace).with_for_update()).first()
            if not member or (member.expires_at and member.expires_at <= now()):
                raise HTTPException(401, 'Your demo session ended. Sign in again to start a fresh workspace.')
            state = session.get(AppState, workspace)
            cutoff = now() - timedelta(seconds=app.state.settings.job_timeout + app.state.settings.inference_timeout + 30)
            active = session.exec(select(Job).where(Job.status.in_(['queued', 'running']))).all()
            for prior in active:
                if prior.created_at >= cutoff:
                    raise HTTPException(409, 'Another triage or index rebuild is running. Wait for it to finish.')
                prior.status = 'failed'
                prior.error = 'This operation was interrupted or timed out. Retry explicitly.'
                prior.finished_at = now()
                session.add(prior)
                recover_interrupted(session, prior)
            if kind == 'rag' and (not state.index_id or state.knowledge_version != state.index_knowledge_version or state.embedding_model != app.state.settings.embedding_model):
                raise HTTPException(409, 'The knowledge index is missing or stale. Rebuild it in Knowledge base before running RAG.')
            ticket = session.get(Ticket, ticket_id) if ticket_id else None
            if ticket_id and (ticket is None or ticket.workspace_id != workspace):
                raise HTTPException(404, 'Ticket not found')
            if kind in ['resolve', 'revise']:
                ticket.resolution_state = 'processing'
                ticket.outcome_version += 1
                ticket.draft_run_id = None
                session.add(ticket)
            snapshot = {
                'ticket': ticket.model_copy(deep=True) if ticket else None,
                'categories': [c.model_copy(deep=True) for c in session.exec(select(Category).where(Category.active == True)).all()],
                'state': state.model_copy(deep=True),
                'is_demo': is_demo,
                'conversation': [{'author': m.author, 'body': m.body} for m in session.exec(select(TicketMessage).where(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at, TicketMessage.id)).all()] if ticket else [],
                'articles': [a.model_copy(deep=True) for a in session.exec(select(Article).where(Article.workspace_id == workspace, Article.active == True)).all()] if kind == 'reindex' else [],
            }
            if kind == 'reindex' and not any(a.is_policy for a in snapshot['articles']):
                raise HTTPException(409, 'Add an article marked as an urgency policy before rebuilding the index.')
            if kind == 'reindex' and not any(not a.is_policy for a in snapshot['articles']):
                raise HTTPException(409, 'Add at least one support article before rebuilding the index.')
            if kind == 'rag' and not snapshot['categories']:
                raise HTTPException(409, 'Add an active category and queue in Settings before running triage.')
            job = Job(id=uuid4().hex, kind=kind, ticket_id=ticket_id, workspace_id=workspace)
            if kind in ['resolve', 'revise']:
                job.result = {'outcome_version': ticket.outcome_version}
            session.add(job)
            session.commit()
            session.refresh(job)
            result = job.model_dump(mode='json')
        app.state.busy = True
    # Complete work inside the request: serverless instances can stop after a response.
    execute(app, result['id'], snapshot)
    with Session(app.state.engine) as session:
        completed = session.get(Job, result['id'])
        if completed is None:
            raise HTTPException(401, 'Your demo session ended and its data was cleared.')
        return completed.model_dump(mode='json')


def execute(app, job_id, snapshot):
    engine = app.state.engine
    ticket = snapshot['ticket']
    state = snapshot['state']
    gateway = BudgetedGateway(app, state.id, snapshot.get('is_demo', False))
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
            index_id, count = app.state.store.build(snapshot['articles'], gateway, progress)
            with Session(engine) as session:
                current = session.get(AppState, state.id)
                if current.knowledge_version != state.knowledge_version:
                    raise ValueError('Knowledge changed while indexing. The prior index was preserved; rebuild again.')
                current.index_id = index_id
                current.index_knowledge_version = state.knowledge_version
                current.embedding_model = app.state.settings.embedding_model
                session.add(current)
                session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.article_id.in_(
                    select(Article.id).where(Article.workspace_id == state.id)), KnowledgeChunk.index_id != index_id))
                session.add(AuditEvent(workspace_id=state.id, actor='demo' if snapshot.get('is_demo') else 'admin', action='index_activated', detail={'index_id': index_id, 'chunks': count, 'knowledge_version': state.knowledge_version}))
                job = session.get(Job, job_id)
                job.result = {'index_id': index_id, 'chunks': count}
                job.status = 'succeeded'
                job.progress = f'Indexed {count} chunks successfully'
                job.finished_at = now()
                session.add(job)
                session.commit()
        else:
            resolving = kind in ['resolve', 'revise']
            if resolving:
                ready = (state.index_id and state.knowledge_version == state.index_knowledge_version
                         and state.embedding_model == app.state.settings.embedding_model)
                reason = risk_reason(f'{ticket.subject}\n{ticket.body}')
                payload = needs_review(reason) if reason else (run_resolution(ticket, snapshot['categories'], state, gateway, app.state.store,
                                         app.state.settings, progress, snapshot.get('conversation', [])) if ready else needs_review('knowledge_unavailable'))
            else:
                payload = run_rules(ticket, snapshot['categories']) if kind == 'rules' else run_rag(
                    ticket, snapshot['categories'], state, gateway, app.state.store, app.state.settings, progress)
            result_id = uuid4().hex
            with Session(engine) as session:
                session.add(RecommendationRun(id=result_id, ticket_id=ticket.id, ticket_revision=ticket.revision,
                    taxonomy_version=state.taxonomy_version, index_version=state.index_id if kind != 'rules' else None,
                    method=kind, model=app.state.settings.generation_model if kind != 'rules' else 'deterministic-keywords-v1',
                    outcome=payload['outcome'], payload=payload))
                if resolving:
                    current = session.exec(select(Ticket).where(Ticket.id == ticket.id).with_for_update()).one()
                    latest = session.get(AppState, state.id)
                    if current.outcome_version != ticket.outcome_version or current.revision != ticket.revision:
                        raise ValueError('A newer customer or administrator update superseded this answer.')
                    if (latest.knowledge_version != state.knowledge_version or latest.index_id != state.index_id
                            or latest.taxonomy_version != state.taxonomy_version):
                        raise ValueError('Knowledge or routing changed while the answer was being written. Review is required.')
                    current.updated_at = now()
                    current.outcome_version += 1
                    if payload['outcome'] == 'suggested' and kind == 'resolve':
                        labels = payload['suggestions']
                        current.category_id, current.priority, current.queue_id = labels['category_id'], labels['priority'], labels['queue_id']
                        current.answer = payload['answer']
                        current.status, current.resolution_state, current.review_reason = 'resolved', 'resolved_ai', ''
                        session.add(TicketMessage(ticket_id=ticket.id, author='assistant', kind='answer', body=payload['answer'], citations=payload['answer_citations']))
                        session.add(Decision(ticket_id=ticket.id, ticket_revision=ticket.revision, recommendation_id=result_id,
                            **labels, action='automated', note='Grounded informational answer; no external action executed.'))
                    elif payload['outcome'] == 'suggested':
                        current.status, current.resolution_state, current.review_reason = 'open', 'changes_requested', 'policy_exception'
                        current.draft_run_id = result_id
                    else:
                        current.status, current.resolution_state = 'open', 'needs_review'
                        current.review_reason = payload['reason_code']
                        session.add(TicketMessage(ticket_id=ticket.id, author='system', kind='handoff',
                            body='Your enquiry is with the support team. ' + REASONS.get(payload['reason_code'], REASONS['insufficient_evidence'])))
                    session.add(current)
                session.add(AuditEvent(workspace_id=state.id, actor='demo' if snapshot.get('is_demo') else 'admin', ticket_id=ticket.id, action='triage_completed', detail={'method': kind, 'outcome': payload['outcome'], 'recommendation_id': result_id}))
                job = session.get(Job, job_id)
                job.result = {'recommendation_id': result_id}
                job.status = 'needs_review' if payload['outcome'] == 'needs_review' else 'succeeded'
                job.progress = ('Enquiry answered automatically' if kind == 'resolve' else 'Revised draft ready for administrator review') if resolving and payload['outcome'] == 'suggested' else ('Human confirmation required' if payload['outcome'] == 'suggested' else 'Support team review required')
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
                    taxonomy_version=state.taxonomy_version, index_version=state.index_id if job.kind != 'rules' else None,
                    method=job.kind, model=app.state.settings.generation_model if job.kind != 'rules' else 'deterministic-keywords-v1',
                    outcome='failed', payload={'outcome': 'failed', 'suggestions': None, 'error': message, 'citations': [], 'retrieved': [], 'sources': [], 'scores': {}, 'rationales': {'review': message}}))
                job.result = {'recommendation_id': result_id}
                if job.kind in ['resolve', 'revise']:
                    current = session.exec(select(Ticket).where(Ticket.id == ticket.id).with_for_update()).first()
                    if current and current.outcome_version == ticket.outcome_version and current.resolution_state == 'processing':
                        current.status, current.resolution_state = 'open', 'needs_review'
                        current.review_reason = 'provider_unavailable'
                        current.outcome_version += 1
                        current.updated_at = now()
                        session.add(current)
                        session.add(TicketMessage(ticket_id=ticket.id, author='system', kind='handoff', body=REASONS['provider_unavailable']))
            job.status = 'failed'
            job.error = message
            job.progress = 'Operation failed; retry is available'
            job.finished_at = now()
            session.add(job)
            session.add(AuditEvent(workspace_id=state.id, actor='demo' if snapshot.get('is_demo') else 'admin', ticket_id=ticket.id if ticket else None, action='job_failed', detail={'job_id': job_id, 'error': message}))
            session.commit()
    finally:
        with app.state.job_lock:
            app.state.busy = False
        with Session(engine) as session:
            cleanup_expired(session)
            session.commit()
