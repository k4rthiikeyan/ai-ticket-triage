"""Session-owned demo workspaces; owner data always remains in workspace 1."""
from datetime import timedelta
from sqlalchemy import delete
from sqlmodel import select
from ..models import Workspace, AppState, LoginSession, Ticket, Article, Job, Decision, Note, AuditEvent, TicketRevision, RecommendationRun, ArticleRevision, KnowledgeChunk, UsageBucket, now


def workspace_id(session):
    return session.info.get('workspace_id', 1)


def state_for(session):
    return session.get(AppState, workspace_id(session))


def create_demo_workspace(session, settings):
    cleanup_expired(session)
    workspace = Workspace(expires_at=now() + timedelta(hours=settings.demo_workspace_hours))
    session.add(workspace)
    session.flush()
    owner = session.get(AppState, 1)
    session.add(AppState(id=workspace.id, taxonomy_version=owner.taxonomy_version))
    return workspace.id


def cleanup_expired(session):
    """Bound each cleanup transaction; remove only expired visitor data, child-first."""
    expired = session.exec(select(Workspace).where(Workspace.expires_at < now()).limit(10)).all()
    for workspace in expired:
        session.exec(delete(AuditEvent).where(AuditEvent.workspace_id == workspace.id))
        ticket_ids = select(Ticket.id).where(Ticket.workspace_id == workspace.id)
        article_ids = select(Article.id).where(Article.workspace_id == workspace.id)
        # Decisions reference runs, so their deletion must happen first.
        for model in [Decision, Note, AuditEvent, TicketRevision, RecommendationRun]:
            session.exec(delete(model).where(model.ticket_id.in_(ticket_ids)))
        session.exec(delete(Job).where(Job.workspace_id == workspace.id))
        session.exec(delete(Ticket).where(Ticket.workspace_id == workspace.id))
        session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.article_id.in_(article_ids)))
        session.exec(delete(ArticleRevision).where(ArticleRevision.article_id.in_(article_ids)))
        session.exec(delete(Article).where(Article.workspace_id == workspace.id))
        session.exec(delete(LoginSession).where(LoginSession.workspace_id == workspace.id))
        session.exec(delete(AppState).where(AppState.id == workspace.id))
        session.delete(workspace)
    session.exec(delete(UsageBucket).where(UsageBucket.expires_at < now()))


def enforce_size(session, model, limit):
    from fastapi import HTTPException
    from sqlalchemy import func
    session.exec(select(AppState).where(AppState.id == workspace_id(session)).with_for_update()).one()
    count = session.exec(select(func.count()).select_from(model).where(model.workspace_id == workspace_id(session))).one()
    if count >= limit:
        raise HTTPException(429, f'This demo workspace allows up to {limit} {model.__name__.lower()}s. Use the existing examples.')
