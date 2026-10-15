from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from ..models import Article, ArticleRevision, now
from ..schemas import ArticleBody, ArticleUpdate, KnowledgeSearch
from ..dependencies import DB, authenticated, found
from ..services.records import audit, changed_knowledge
from ..jobs import enqueue, readable_error
from ..rag import embed_query
from ..services.workspaces import workspace_id, state_for, enforce_size
from ..services.usage import BudgetedGateway


def register(app):
    settings = app.state.settings
    router = APIRouter(prefix="/api", dependencies=[Depends(authenticated)])

    @router.get('/articles')
    def articles(session: DB):
        return session.exec(select(Article).where(Article.workspace_id == workspace_id(session)).order_by(Article.is_policy.desc(), Article.title)).all()


    @router.get('/articles/{identifier}/revisions')
    def article_history(identifier: str, session: DB):
        found(session, Article, identifier)
        return session.exec(select(ArticleRevision).where(ArticleRevision.article_id == identifier).order_by(ArticleRevision.revision.desc())).all()


    @router.post('/articles', status_code=201)
    def add_article(body: ArticleBody, session: DB):
        if session.info.get('is_demo'):
            enforce_size(session, Article, settings.demo_article_limit)
        article = Article(id='article-' + uuid4().hex[:12], workspace_id=workspace_id(session), **body.model_dump())
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
    def reindex(session: DB):
        return enqueue(app, 'reindex', workspace=workspace_id(session), is_demo=session.info.get('is_demo', False))


    @router.post('/knowledge/search')
    def search_knowledge(body: KnowledgeSearch, session: DB):
        state = state_for(session)
        if not state.index_id or state.knowledge_version != state.index_knowledge_version or state.embedding_model != settings.embedding_model:
            raise HTTPException(409, 'Add your knowledge and rebuild the index before searching.')
        try:
            vector = embed_query(body.query, BudgetedGateway(app, workspace_id(session), session.info.get('is_demo', False)))
            results, _ = app.state.store.retrieve(state.index_id, vector, top_k=body.limit)
            return {'items': [source for source in results if source['similarity'] >= settings.retrieval_threshold],
                    'index_id': state.index_id, 'embedding_model': settings.embedding_model}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(502, readable_error(error)) from error


    app.include_router(router)
