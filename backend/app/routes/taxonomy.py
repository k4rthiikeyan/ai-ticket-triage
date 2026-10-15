from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from ..models import Category, Queue
from ..schemas import CategoryBody, QueueBody
from ..dependencies import DB, authenticated, administrator, found
from ..services.records import audit, changed_knowledge


def register(app):
    settings = app.state.settings
    router = APIRouter(prefix="/api", dependencies=[Depends(authenticated)])

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


    app.include_router(router)
