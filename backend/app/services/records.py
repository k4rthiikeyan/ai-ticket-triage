from sqlalchemy import update
from ..models import AppState, AuditEvent, Category, Queue
from .workspaces import workspace_id
def changed_knowledge(session, taxonomy=False):
    values = {'knowledge_version': AppState.knowledge_version + 1}
    if taxonomy:
        values['taxonomy_version'] = AppState.taxonomy_version + 1
    statement = update(AppState)
    if not taxonomy:
        statement = statement.where(AppState.id == workspace_id(session))
    session.exec(statement.values(**values))


def audit(session, action, detail, ticket_id=None):
    session.add(AuditEvent(ticket_id=ticket_id, workspace_id=workspace_id(session),
                           actor='demo' if session.info.get('is_demo') else 'admin', action=action, detail=detail))


def ticket_data(ticket, session):
    data = ticket.model_dump(mode='json')
    category = session.get(Category, ticket.category_id) if ticket.category_id else None
    queue = session.get(Queue, ticket.queue_id) if ticket.queue_id else None
    data.update(category_name=category.name if category else None, queue_name=queue.name if queue else None)
    return data


