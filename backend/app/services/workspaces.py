"""Session-owned demo workspaces; owner data always remains in workspace 1."""
from datetime import timedelta
from sqlalchemy import delete, update
from sqlmodel import select
from ..models import Workspace, AppState, LoginSession, Ticket, Article, Job, Decision, Note, AuditEvent, TicketRevision, RecommendationRun, ArticleRevision, KnowledgeChunk, UsageBucket, CustomerSession, TicketMessage, now


def workspace_id(session):
    return session.info.get('workspace_id', 1)


def state_for(session):
    return session.get(AppState, workspace_id(session))


def shorten_legacy_sessions(session, settings):
    deadline = now() + timedelta(minutes=settings.demo_idle_minutes)
    session.exec(update(Workspace).where(Workspace.id != 1, Workspace.expires_at > deadline).values(expires_at=deadline))
    session.exec(update(LoginSession).where(LoginSession.workspace_id != 1, LoginSession.expires_at > deadline).values(expires_at=deadline))


def create_demo_workspace(session, settings, starter_examples=True):
    cleanup_expired(session)
    workspace = Workspace(expires_at=now() + timedelta(minutes=settings.demo_idle_minutes))
    session.add(workspace)
    session.flush()
    owner = session.get(AppState, 1)
    session.add(AppState(id=workspace.id, taxonomy_version=owner.taxonomy_version))
    session.flush()
    if starter_examples:
        from .examples import load_examples
        load_examples(session, workspace.id)
    return workspace.id


def delete_workspace(session, identifier):
    """Delete all visitor data, deferring only while an admitted operation is running."""
    if identifier == 1:
        raise ValueError('Owner data cannot be deleted through demo cleanup.')
    workspace = session.exec(select(Workspace).where(Workspace.id == identifier).with_for_update()).first()
    if not workspace or workspace.expires_at is None:
        return False
    workspace.expires_at = now()
    session.add(workspace)
    # An in-flight provider request must finish before its output rows can be purged.
    cutoff = now() - timedelta(minutes=6)
    active = session.exec(select(Job.id).where(Job.workspace_id == identifier,
        Job.status.in_(['queued', 'running']), Job.created_at >= cutoff)).first()
    session.exec(delete(LoginSession).where(LoginSession.workspace_id == identifier))
    session.exec(delete(CustomerSession).where(CustomerSession.workspace_id == identifier))
    if active:
        return False
    session.exec(delete(AuditEvent).where(AuditEvent.workspace_id == identifier))
    ticket_ids = select(Ticket.id).where(Ticket.workspace_id == identifier)
    article_ids = select(Article.id).where(Article.workspace_id == identifier)
    for model in [TicketMessage, Decision, Note, AuditEvent, TicketRevision, RecommendationRun]:
        session.exec(delete(model).where(model.ticket_id.in_(ticket_ids)))
    session.exec(delete(Job).where(Job.workspace_id == identifier))
    session.exec(delete(Ticket).where(Ticket.workspace_id == identifier))
    session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.article_id.in_(article_ids)))
    session.exec(delete(ArticleRevision).where(ArticleRevision.article_id.in_(article_ids)))
    session.exec(delete(Article).where(Article.workspace_id == identifier))
    session.exec(delete(AppState).where(AppState.id == identifier))
    session.delete(workspace)
    return True


def cleanup_expired(session):
    """Bound each cleanup transaction; remove only expired visitor data, child-first."""
    expired = session.exec(select(Workspace).where(Workspace.id != 1, Workspace.expires_at < now())
                           .with_for_update(skip_locked=True).limit(10)).all()
    for workspace in expired:
        delete_workspace(session, workspace.id)
    session.exec(delete(UsageBucket).where(UsageBucket.expires_at < now()))
    session.exec(delete(CustomerSession).where(CustomerSession.expires_at < now()))


def enforce_size(session, model, limit):
    from fastapi import HTTPException
    from sqlalchemy import func
    if not session.exec(select(AppState).where(AppState.id == workspace_id(session)).with_for_update()).first():
        raise HTTPException(401, 'Your demo session ended. Sign in again to continue.')
    count = session.exec(select(func.count()).select_from(model).where(model.workspace_id == workspace_id(session))).one()
    if count >= limit:
        raise HTTPException(429, f'This demo workspace allows up to {limit} {model.__name__.lower()}s. Use the existing examples.')
