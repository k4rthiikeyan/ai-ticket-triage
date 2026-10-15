from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.models import (Workspace, LoginSession, Article, Ticket, Job, KnowledgeChunk,
    ArticleRevision, TicketRevision, Note, Decision, RecommendationRun, AuditEvent, now)
from backend.app.rag import VectorStore
from .test_demo_access import enable_demo, sign_in_demo
from .conftest import create_ticket


def test_default_demo_has_labelled_examples_without_ai_requests(workspace, monkeypatch):
    app, client, _ = enable_demo(workspace)
    monkeypatch.setattr(app.state.gateway, 'embed', lambda _: (_ for _ in ()).throw(AssertionError('No embeddings during login')))
    login = client.post('/api/auth/login', json={'username': 'demo', 'password': 'try-triage'})
    assert login.status_code == 200
    cookie = login.headers['set-cookie'].lower()
    assert 'max-age=' not in cookie and 'expires=' not in cookie
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    client.headers['X-CSRF-Token'] = login.json()['csrf_token']
    articles = client.get('/api/articles').json()
    tickets = client.get('/api/tickets').json()['items']
    assert len(articles) == 6 and sum(a['is_policy'] for a in articles) == 1
    assert len(tickets) == 3 and all(t['status'] == 'new' for t in tickets)
    assert all(a['title'].startswith('Example') for a in articles)
    assert all(t['subject'].startswith('Example') for t in tickets)
    assert not client.get('/api/system').json()['index_ready']
    # Re-login and repeated explicit loading do not duplicate or overwrite examples.
    sign_in_demo(client, starter_examples=True)
    assert client.post('/api/demo/examples').json() == {'articles': 0, 'tickets': 0}
    assert client.get('/api/tickets').json()['total'] == 3
    owner = TestClient(app)
    owner.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'})
    assert owner.get('/api/tickets').json()['total'] == 0
    assert owner.get('/api/articles').json() == []


def test_logout_removes_text_revisions_decisions_sessions_and_embeddings(workspace):
    app, client, _ = enable_demo(workspace)
    app.state.store = VectorStore(app.state.engine)
    owner_login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
    client.headers['X-CSRF-Token'] = owner_login['csrf_token']
    owner_ticket = create_ticket(client)
    visitor = TestClient(app)
    sign_in_demo(visitor, starter_examples=True)
    assert visitor.post('/api/knowledge/reindex').json()['status'] == 'succeeded'
    tickets = visitor.get('/api/tickets').json()['items']
    ticket = next(t for t in tickets if 'Refund' in t['subject'])
    article_ids = [a['id'] for a in visitor.get('/api/articles').json()]
    job = visitor.post(f"/api/tickets/{ticket['id']}/triage").json()
    assert job['status'] == 'succeeded', job
    run = visitor.get(f"/api/tickets/{ticket['id']}").json()['runs'][0]
    assert visitor.post(f"/api/tickets/{ticket['id']}/decisions", json={
        'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}).status_code == 201
    assert visitor.post(f"/api/tickets/{ticket['id']}/notes", json={'body': 'Temporary demo note.'}).status_code == 201
    with Session(app.state.engine) as session:
        identifier = session.exec(select(Workspace.id).where(Workspace.id != 1)).one()
        assert session.exec(select(KnowledgeChunk).where(KnowledgeChunk.article_id.in_(article_ids))).all()
    response = visitor.post('/api/auth/logout')
    assert response.status_code == 200 and 'max-age=0' in response.headers['set-cookie'].lower()
    assert visitor.get('/api/tickets').status_code == 401
    with Session(app.state.engine) as session:
        assert session.get(Workspace, identifier) is None
        for model in [Ticket, Article, Job, AuditEvent, LoginSession]:
            assert not session.exec(select(model).where(model.workspace_id == identifier)).all()
        for model in [TicketRevision, Note, Decision, RecommendationRun]:
            assert not session.exec(select(model).where(model.ticket_id.in_([t['id'] for t in tickets]))).all()
        assert not session.exec(select(KnowledgeChunk).where(KnowledgeChunk.article_id.in_(article_ids))).all()
        assert not session.exec(select(ArticleRevision).where(ArticleRevision.article_id.in_(article_ids))).all()
        assert session.get(Ticket, owner_ticket['id']) is not None


def test_demo_activity_extends_short_expiry_and_idle_cleanup_removes_index(workspace):
    app, client, settings = enable_demo(workspace)
    app.state.store = VectorStore(app.state.engine)
    sign_in_demo(client, starter_examples=True)
    assert client.post('/api/knowledge/reindex').json()['status'] == 'succeeded'
    with Session(app.state.engine) as session:
        row = session.exec(select(Workspace).where(Workspace.id != 1)).one()
        identifier = row.id
        row.expires_at = now() + timedelta(minutes=1)
        session.add(row)
        session.commit()
    assert client.get('/api/auth/me').status_code == 200
    with Session(app.state.engine) as session:
        row = session.get(Workspace, identifier)
        assert row.expires_at > now() + timedelta(minutes=settings.demo_idle_minutes - 1)
        row.expires_at = now() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    assert client.get('/api/tickets').status_code == 401
    with Session(app.state.engine) as session:
        assert session.get(Workspace, identifier) is None
        assert not session.exec(select(KnowledgeChunk)).all()


def test_logout_during_indexing_purges_output_after_request_finishes(workspace, monkeypatch):
    app, client, _ = enable_demo(workspace)
    app.state.store = VectorStore(app.state.engine)
    sign_in_demo(client, starter_examples=True)
    started, release = Event(), Event()
    def blocking_embed(texts):
        started.set()
        assert release.wait(10)
        return [[1., 0., 0.] for _ in texts]
    monkeypatch.setattr(app.state.gateway, 'embed', blocking_embed)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, '/api/knowledge/reindex')
        try:
            assert started.wait(3)
            assert client.post('/api/auth/logout').status_code == 200
            with Session(app.state.engine) as session:
                assert not session.exec(select(LoginSession)).all()
        finally:
            release.set()
        assert pending.result().status_code == 401
    with Session(app.state.engine) as session:
        assert session.exec(select(Workspace.id)).all() == [1]
        assert not session.exec(select(KnowledgeChunk)).all()
        assert not session.exec(select(Article)).all()
