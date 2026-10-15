from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.models import Workspace, UsageBucket, AppState, LoginSession, now
from backend.app.rag import VectorStore
from backend.app.services.usage import BudgetedGateway, consume
from .conftest import create_ticket
from .test_demo_access import enable_demo, sign_in_demo


def visitor(app):
    client = TestClient(app)
    sign_in_demo(client)
    return client


def add_knowledge(client):
    ids = []
    for article in [
        {'title': 'Visitor billing', 'body': 'Duplicate charges belong to Billing. Investigate the payment request.'},
        {'title': 'Visitor urgency', 'body': 'Routine billing requests have normal priority.', 'is_policy': True},
    ]:
        response = client.post('/api/articles', json=article)
        assert response.status_code == 201, response.text
        ids.append(response.json()['id'])
    return ids


def test_two_visitors_and_owner_are_isolated_end_to_end(signed):
    app, owner, *_ = signed
    enable_demo(signed)
    app.state.store = VectorStore(app.state.engine)
    owner_ticket = create_ticket(owner)
    first, second = visitor(app), visitor(app)
    assert first.get('/api/tickets').json()['total'] == 0
    assert first.get('/api/articles').json() == []
    assert first.get('/api/tickets/' + str(owner_ticket['id'])).status_code == 404
    ids = add_knowledge(first)
    assert not second.get('/api/system').json()['index_ready']
    indexed = first.post('/api/knowledge/reindex').json()
    assert indexed['status'] == 'succeeded', indexed
    ticket = create_ticket(first)
    run_job = first.post(f"/api/tickets/{ticket['id']}/triage").json()
    assert run_job['status'] == 'succeeded', run_job
    run = first.get(f"/api/tickets/{ticket['id']}").json()['runs'][0]
    assert {s['article_id'] for s in run['payload']['sources']} == set(ids)
    assert first.post(f"/api/tickets/{ticket['id']}/decisions", json={
        'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}).status_code == 201
    for client in [second, owner]:
        assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404
        assert client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'body': 'Forbidden cross-workspace change'}).status_code == 404
        assert client.post(f"/api/tickets/{ticket['id']}/notes", json={'body': 'Forbidden cross-workspace note'}).status_code == 404
        assert client.post(f"/api/tickets/{ticket['id']}/triage?method=rules").status_code == 404
        assert client.get('/api/articles/' + ids[0] + '/revisions').status_code == 404
        assert client.get('/api/jobs/' + run_job['id']).status_code == 404
    assert second.get('/api/dashboard').json()['total'] == 0
    assert second.get('/api/system').json()['jobs'] == []
    assert not owner.get('/api/system').json()['index_ready']
    # Reload and a renewed login in the same unexpired browser retain its workspace.
    sign_in_demo(first)
    assert first.get(f"/api/tickets/{ticket['id']}").json()['ticket']['status'] == 'open'


def test_expired_demo_workspace_is_rejected_and_cleaned(workspace):
    app, *_ = enable_demo(workspace)
    first = visitor(app)
    ticket = create_ticket(first)
    add_knowledge(first)
    assert first.post('/api/knowledge/reindex').json()['status'] == 'succeeded'
    with Session(app.state.engine) as session:
        row = session.exec(select(Workspace).where(Workspace.id != 1)).one()
        expired_id = row.id
        row.expires_at = now() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    assert first.get('/api/tickets').status_code == 401
    sign_in_demo(first)
    assert first.get('/api/tickets').json()['total'] == 0
    assert first.get('/api/tickets/' + str(ticket['id'])).status_code == 404
    with Session(app.state.engine) as session:
        assert session.get(Workspace, expired_id) is None
        assert session.get(AppState, 1) is not None


def test_demo_size_and_ai_limits_do_not_call_provider_after_exhaustion(workspace, monkeypatch):
    app, _, settings = enable_demo(workspace)
    settings.demo_ticket_limit = 1
    settings.demo_ai_daily_limit = 1
    first = visitor(app)
    create_ticket(first)
    assert first.post('/api/tickets', json={'subject': 'Another ticket', 'body': 'A request exceeding the workspace limit.'}).status_code == 429
    with Session(app.state.engine) as session:
        identifier = session.exec(select(Workspace.id).where(Workspace.id != 1)).one()
    calls = []
    monkeypatch.setattr(app.state.gateway, 'embed', lambda texts: calls.append(texts) or [[1., 0.]])
    gateway = BudgetedGateway(app, identifier, True)
    gateway.embed(['first call'])
    with pytest.raises(HTTPException) as rejected:
        gateway.embed(['must not reach provider'])
    assert rejected.value.status_code == 429
    assert len(calls) == 1


def test_usage_counter_is_atomic_across_independent_sessions(workspace):
    app = workspace[0]
    def attempt(_):
        with Session(app.state.engine) as session:
            try:
                consume(session, 'concurrency-test', 3, 86400)
                session.commit()
                return True
            except HTTPException:
                session.rollback()
                return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(12))) == 3
    with Session(app.state.engine) as session:
        assert session.exec(select(UsageBucket.count)).all() == [3]


def test_legacy_demo_token_can_never_read_owner_workspace(workspace):
    app, *_ = enable_demo(workspace)
    first = visitor(app)
    with Session(app.state.engine) as session:
        login = session.exec(select(LoginSession)).one()
        login.workspace_id = 1
        session.add(login)
        session.commit()
    assert first.get('/api/tickets').status_code == 401
    sign_in_demo(first)
    assert first.get('/api/tickets').json()['total'] == 0
