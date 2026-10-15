import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.rag import OpenRouterError
from sqlmodel import Session, select
from backend.app.main import create_app
from backend.app.models import Job, Ticket, Article, Admin, Queue, now
from datetime import timedelta
from backend.app.seed import seed
from .conftest import create_ticket, triage, reindex, wait_job


@pytest.mark.parametrize('path', ['/tickets', '/dashboard', '/articles', '/taxonomy', '/docs', '/openapi.json', '/system', '/jobs/unknown'])
def test_data_and_docs_require_login(workspace, path):
    assert workspace[1].get('/api' + path).status_code == 401


def test_login_csrf_origin_and_logout(workspace):
    app, client, *_ = workspace
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'bad'}).status_code == 401
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'})
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/api/auth/me').json()['username'] == 'admin'
    assert client.post('/api/tickets', json={'subject': 'Valid title', 'body': 'A valid synthetic customer request.'}).status_code == 403
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    assert client.post('/api/tickets', headers={'Origin': 'https://malicious.example'}, json={'subject': 'Valid title', 'body': 'A valid synthetic customer request.'}).status_code == 403
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/tickets').status_code == 401


def test_live_provider_check_requires_auth_and_csrf(workspace):
    _, client, *_ = workspace
    assert client.post('/api/system/check-provider?kind=embeddings').status_code == 401
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'})
    assert response.status_code == 200
    assert client.post('/api/system/check-provider?kind=embeddings').status_code == 403


def test_live_provider_check_does_not_add_workspace_data(signed):
    _, client, gateway, *_ = signed
    tickets_before = client.get('/api/tickets').json()['total']
    articles_before = client.get('/api/articles').json()
    embedding = client.post('/api/system/check-provider?kind=embeddings').json()
    assert embedding['available'] and embedding['dimensions'] == 3 and embedding['free_only']
    gateway.raw = '{"connected":true}'
    generation = client.post('/api/system/check-provider?kind=llm').json()
    assert generation['available'] and generation['free_only']
    assert client.get('/api/tickets').json()['total'] == tickets_before
    assert client.get('/api/articles').json() == articles_before
    gateway.failure = OpenRouterError('OpenRouter: Free-model quota or rate limit reached.')
    failure = client.post('/api/system/check-provider?kind=embeddings').json()
    assert not failure['available'] and 'quota' in failure['message']
    gateway.failure = None
    gateway.raw = 'not JSON'
    assert not client.post('/api/system/check-provider?kind=llm').json()['available']
    assert client.post('/api/system/check-provider?kind=other').status_code == 422


def test_create_search_filter_and_validation(signed):
    app, client, *_ = signed
    before = client.get('/api/dashboard').json()['total']
    ticket = create_ticket(client)
    assert ticket['status'] == 'new' and ticket['category_id'] is None
    assert client.get('/api/tickets', params={'q': 'DUPLICATE', 'status': 'new'}).json()['total'] >= 1
    assert client.get('/api/tickets', params={'q': '#' + str(ticket['id'])}).json()['items'][0]['id'] == ticket['id']
    assert client.get('/api/tickets', params={'limit': 2}).json()['limit'] == 2
    assert client.post('/api/tickets', json={'subject': 'x', 'body': 'short'}).status_code == 422
    assert client.get('/api/dashboard').json()['total'] == before + 1
    assert client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'status': 'resolved'}).status_code == 409


def test_rules_accept_override_and_status(signed):
    app, client, *_ = signed
    ticket = create_ticket(client)
    job, run = triage(client, app, ticket['id'])
    assert job['status'] == 'succeeded' and run['payload']['rationales']['category'].startswith('Matched keywords:')
    assert client.get(f"/api/tickets/{ticket['id']}").json()['ticket']['category_id'] is None
    final = {'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}
    assert client.post(f"/api/tickets/{ticket['id']}/decisions", json=final).json()['action'] == 'accepted'
    assert client.post(f"/api/tickets/{ticket['id']}/decisions", json={**final, 'priority': 'high', 'note': 'Impact clarified by operator'}).json()['action'] == 'overridden'
    assert client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'status': 'resolved'}).json()['status'] == 'resolved'
    assert client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'status': 'open'}).json()['status'] == 'open'
    detail = client.get(f"/api/tickets/{ticket['id']}").json()
    assert any(e['action'] == 'decision_overridden' for e in detail['audit'])
    assert client.get('/api/tickets', params={'priority': 'high', 'category_id': final['category_id'], 'queue_id': final['queue_id']}).json()['total'] >= 1


def test_revision_invalidates_labels_and_stale_acceptance(signed):
    app, client, *_ = signed
    ticket = create_ticket(client)
    _, run = triage(client, app, ticket['id'])
    final = {'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}
    client.post(f"/api/tickets/{ticket['id']}/decisions", json=final)
    updated = client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'body': 'My password expired and I cannot work without account access.'}).json()
    assert updated['revision'] == 2 and updated['status'] == 'new' and updated['category_id'] is None
    assert updated['original_body'] == ticket['body']
    assert client.post(f"/api/tickets/{ticket['id']}/decisions", json={**final, 'expected_revision': 2}).status_code == 409
    detail = client.get(f"/api/tickets/{ticket['id']}").json()
    assert len(detail['revisions']) == 2 and detail['runs'][0]['stale']
    assert client.patch(f"/api/tickets/{ticket['id']}", json={'expected_revision': 1, 'subject': 'Changed title'}).status_code == 409


def test_manual_decision_notes_and_untriaged_bucket(signed):
    app, client, *_ = signed
    ticket = create_ticket(client, 'Unclear issue', 'I need help but do not know the cause yet.')
    _, run = triage(client, app, ticket['id'])
    assert run['outcome'] == 'needs_review'
    assert any(c['name'] == 'Untriaged' and c['count'] >= 1 for c in client.get('/api/dashboard').json()['categories'])
    category = client.get('/api/taxonomy').json()['categories'][0]
    response = client.post(f"/api/tickets/{ticket['id']}/decisions", json={'expected_revision': 1, 'category_id': category['id'], 'queue_id': category['queue_id'], 'priority': 'normal'})
    assert response.json()['action'] == 'manual'
    assert client.post(f"/api/tickets/{ticket['id']}/notes", json={'body': 'Only internal context.'}).status_code == 201
    detail = client.get(f"/api/tickets/{ticket['id']}").json()
    assert detail['notes'][0]['body'] == 'Only internal context.'
    assert any(e['action'] == 'note_added' for e in detail['audit'])


def test_index_lifecycle_article_revisions_and_archive(signed):
    app, client, gateway, store, _ = signed
    assert not client.get('/api/system').json()['index_ready']
    assert reindex(client, app)['status'] == 'succeeded'
    original_index = client.get('/api/system').json()['index_id']
    assert client.get('/api/system').json()['index_ready']
    article = client.post('/api/articles', json={'title': 'Synthetic article', 'body': 'A new support policy describing a billing question for this fictional demo.'}).json()
    assert not client.get('/api/system').json()['index_ready']
    assert client.post('/api/tickets/1/triage').status_code == 404
    assert client.patch('/api/articles/' + article['id'], json={'expected_revision': 1, 'title': article['title'], 'body': article['body'] + ' Updated.', 'active': False}).json()['revision'] == 2
    assert len(client.get('/api/articles/' + article['id'] + '/revisions').json()) == 2
    assert client.patch('/api/articles/' + article['id'], json={'expected_revision': 1, 'title': article['title'], 'body': article['body']}).status_code == 409
    policy = next(a for a in client.get('/api/articles').json() if a['is_policy'])
    assert client.patch('/api/articles/' + policy['id'], json={'expected_revision': 1, 'title': policy['title'], 'body': policy['body'], 'active': False}).status_code == 409
    store.failure = True
    assert reindex(client, app)['status'] == 'failed'
    assert client.get('/api/system').json()['index_id'] == original_index
    assert not client.get('/api/system').json()['index_ready']
    store.failure = False
    assert reindex(client, app)['status'] == 'succeeded'
    assert client.get('/api/system').json()['index_id'] != original_index


def test_rag_citations_scores_and_confirmation(signed):
    app, client, *_ = signed
    reindex(client, app)
    ticket = create_ticket(client)
    job, run = triage(client, app, ticket['id'], 'rag')
    assert job['status'] == 'succeeded'
    assert len(run['payload']['citations']) == 2
    assert run['payload']['scores'] == {'category': .82, 'priority': .6, 'queue': .82}
    assert run['index_version']
    assert client.post(f"/api/tickets/{ticket['id']}/decisions", json={'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}).json()['action'] == 'accepted'


@pytest.mark.parametrize('failure', [httpx.ReadTimeout('timed out'), httpx.ConnectError('unavailable'), OpenRouterError('OpenRouter model unavailable')])
def test_rag_failures_are_recorded_without_silent_fallback(signed, failure):
    app, client, gateway, _, _ = signed
    reindex(client, app)
    gateway.failure = failure
    ticket = create_ticket(client)
    job, run = triage(client, app, ticket['id'], 'rag')
    assert job['status'] == 'failed' and job['error']
    assert run['method'] == 'rag' and run['outcome'] == 'failed'
    assert client.get(f"/api/tickets/{ticket['id']}").json()['ticket']['status'] == 'new'
    assert triage(client, app, ticket['id'], 'rules')[0]['status'] == 'succeeded'


def test_low_relevance_and_malformed_output(signed):
    app, client, gateway, store, _ = signed
    reindex(client, app)
    ticket = create_ticket(client)
    store.similarity = .1
    assert triage(client, app, ticket['id'], 'rag')[1]['outcome'] == 'needs_review'
    store.similarity = .8
    gateway.raw = 'not JSON'
    assert triage(client, app, ticket['id'], 'rag')[0]['status'] == 'failed'


def test_taxonomy_changes_preserve_history_and_invalidate_runs(signed):
    app, client, *_ = signed
    ticket = create_ticket(client)
    _, run = triage(client, app, ticket['id'])
    taxonomy = client.get('/api/taxonomy').json()
    category = taxonomy['categories'][0]
    final = {'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}
    client.post(f"/api/tickets/{ticket['id']}/decisions", json=final)
    queue = next(q for q in taxonomy['queues'] if q['id'] == category['queue_id'])
    assert client.patch('/api/queues/' + str(queue['id']), json={'name': queue['name'], 'active': False}).status_code == 409
    assert client.patch('/api/categories/' + str(category['id']), json={'name': category['name'], 'queue_id': category['queue_id'], 'keywords': category['keywords'], 'active': False}).status_code == 200
    assert client.get(f"/api/tickets/{ticket['id']}").json()['ticket']['category_name'] == category['name']
    assert client.post(f"/api/tickets/{ticket['id']}/decisions", json=final).status_code == 422
    assert client.post('/api/queues', json={'name': 'New queue'}).status_code == 201
    assert client.post('/api/queues', json={'name': 'New queue'}).status_code == 409


def test_restart_retains_data_marks_jobs_failed_and_seed_is_idempotent(workspace):
    app, client, gateway, store, settings = workspace
    with Session(app.state.engine) as session:
        before = len(session.exec(select(Ticket)).all())
        articles = len(session.exec(select(Article)).all())
        session.add(Job(id='interrupted', kind='reindex', status='running', created_at=now() - timedelta(hours=1)))
        session.commit()
    restarted = create_app(settings, gateway, store)
    with TestClient(restarted) as other:
        auth = other.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
        other.headers['X-CSRF-Token'] = auth['csrf_token']
        assert other.get('/api/dashboard').json()['total'] == before
        assert len(other.get('/api/articles').json()) == articles
        assert other.get('/api/jobs/interrupted').json()['status'] == 'failed'


def test_seeding_keeps_one_admin_when_bootstrap_config_changes(workspace):
    app, _, _, _, settings = workspace
    seed(app.state.engine, settings.model_copy(update={'admin_username': 'another-admin', 'admin_password': 'another-password'}))
    with Session(app.state.engine) as session:
        admins = session.exec(select(Admin)).all()
        assert len(admins) == 1 and admins[0].username == 'admin'


def test_background_operations_are_serialized(signed, monkeypatch):
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    app, client, gateway, _, _ = signed
    started, release = Event(), Event()
    ticket = create_ticket(client)

    def blocking_embed(texts):
        started.set()
        assert release.wait(5), 'Test operation was not released'
        return [[1., 0., 0.] for _ in texts]

    monkeypatch.setattr(gateway, 'embed', blocking_embed)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, '/api/knowledge/reindex')
        try:
            assert started.wait(2)
            assert client.post(f"/api/tickets/{ticket['id']}/triage?method=rules").status_code == 409
            assert client.post('/api/knowledge/reindex').status_code == 409
        finally:
            release.set()
        response = pending.result()
    assert wait_job(client, app, response.json()['id'])['status'] == 'succeeded'


def test_seed_preserves_queue_renames_without_duplicate_defaults(signed):
    app, client, _, _, settings = signed
    queue = client.get('/api/taxonomy').json()['queues'][0]
    assert client.patch('/api/queues/' + str(queue['id']), json={'name': 'Finance support', 'active': True}).status_code == 200
    seed(app.state.engine, settings)
    with Session(app.state.engine) as session:
        queues = session.exec(select(Queue)).all()
        assert len(queues) == 3
        assert session.get(Queue, queue['id']).name == 'Finance support'


def test_fresh_install_is_empty_and_does_not_reseed_content(workspace):
    app, client, _, _, settings = workspace
    auth = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
    client.headers['X-CSRF-Token'] = auth['csrf_token']
    assert client.get('/api/dashboard').json()['total'] == 0
    assert client.get('/api/articles').json() == []
    assert client.post('/api/knowledge/reindex').status_code == 409
    ticket = create_ticket(client, 'User entered ticket', 'This request was entered by the user and must survive restart.')
    article = client.post('/api/articles', json={'title': 'User entered policy', 'body': 'The user defines their own urgency conditions here.', 'is_policy': True}).json()
    seed(app.state.engine, settings)
    assert client.get('/api/dashboard').json()['total'] == 1
    assert client.get('/api/articles').json()[0]['id'] == article['id']
    assert client.get(f"/api/tickets/{ticket['id']}").json()['ticket']['body'] == ticket['body']


def test_semantic_search_and_provider_failures(signed):
    app, client, gateway, store, _ = signed
    assert client.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).status_code == 409
    reindex(client, app)
    response = client.post('/api/knowledge/search', json={'query': 'Duplicate charge', 'limit': 2})
    assert response.status_code == 200
    assert response.json()['items'][0]['text'] == 'Duplicate charges belong to Billing.'
    assert client.post('/api/knowledge/search', json={'query': 'x'}).status_code == 422
    store.similarity = .1
    assert client.post('/api/knowledge/search', json={'query': 'Unrelated request'}).json()['items'] == []
    gateway.failure = OpenRouterError('Set OPENROUTER_API_KEY on the server.')
    response = client.post('/api/knowledge/search', json={'query': 'Duplicate charge'})
    assert response.status_code == 502 and 'OPENROUTER_API_KEY' in response.json()['detail']


def test_cleanup_removes_tagged_demo_records_and_preserves_user_input(signed):
    app, client, _, _, settings = signed
    from backend.app.models import Decision, TicketRevision, AuditEvent
    user = create_ticket(client, 'User entered request', 'Keep this actual user request in the workspace.')
    demo = create_ticket(client, 'Old demo request', 'This record was tagged by the old demonstration seed.')
    _, run = triage(client, app, demo['id'], 'rules')
    # Mark just the legacy ticket as seeded, including associated audit/history records.
    with Session(app.state.engine) as session:
        record = session.get(Ticket, demo['id'])
        record.seed_key = 'demo-1'
        session.add(record)
        session.commit()
    seed(app.state.engine, settings)
    assert client.get(f"/api/tickets/{demo['id']}").status_code == 404
    assert client.get(f"/api/tickets/{user['id']}").status_code == 200
    with Session(app.state.engine) as session:
        assert not session.exec(select(TicketRevision).where(TicketRevision.ticket_id == demo['id'])).all()
        assert not session.exec(select(AuditEvent).where(AuditEvent.ticket_id == demo['id'])).all()


def test_expired_job_can_be_recovered_from_a_warm_instance(signed):
    app, client, *_ = signed
    with Session(app.state.engine) as session:
        session.add(Job(id='expired', kind='reindex', status='running', created_at=now() - timedelta(hours=1)))
        session.commit()
    assert not client.get('/api/system').json()['busy']
    assert client.get('/api/jobs/expired').json()['status'] == 'failed'
    assert reindex(client, app)['status'] == 'succeeded'
