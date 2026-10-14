"""Run against the disposable Postgres service in GitHub CI, never a production DB."""
import os
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session
from backend.app.config import Settings
from backend.app.db import make_engine
from backend.app.main import create_app
from backend.app.models import Job
from .conftest import FakeGateway


@pytest.mark.skipif(not os.environ.get('TEST_POSTGRES_URL'), reason='Disposable Postgres service is not configured')
def test_full_workflow_and_restart_with_real_postgres():
    base = os.environ['TEST_POSTGRES_URL']
    schema = 'triage_test_' + uuid4().hex
    control = make_engine(Settings(database_url=base, _env_file=None))
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    url = make_url(base).update_query_dict({'options': f'-csearch_path={schema}'})
    settings = Settings(database_url=url.render_as_string(hide_password=False), admin_password='test-password', _env_file=None)
    try:
        app = create_app(settings, gateway=FakeGateway())
        with TestClient(app) as client:
            auth = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
            client.headers['X-CSRF-Token'] = auth['csrf_token']
            assert client.get('/api/articles').json() == []
            created_queue = client.post('/api/queues', json={'name': 'User entered queue'})
            assert created_queue.status_code == 201, created_queue.text
            assert created_queue.json()['id'] > 3
            for article in [
                {'title': 'Billing guidance', 'body': 'Duplicate charges belong to Billing. Review the payment request.'},
                {'title': 'Urgency policy', 'body': 'Routine billing requests have normal priority.', 'is_policy': True},
            ]:
                assert client.post('/api/articles', json=article).status_code == 201
            assert client.post('/api/knowledge/reindex').json()['status'] == 'succeeded'
            assert client.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).json()['items']
            ticket = client.post('/api/tickets', json={'subject': 'Duplicate charge', 'body': 'A duplicate charge appeared but the product still works.'}).json()
            job = client.post(f"/api/tickets/{ticket['id']}/triage").json()
            assert job['status'] == 'succeeded', job
            run = client.get(f"/api/tickets/{ticket['id']}").json()['runs'][0]
            assert client.post(f"/api/tickets/{ticket['id']}/decisions", json={
                'expected_revision': 1, 'recommendation_id': run['id'], **run['payload']['suggestions']}).status_code == 201
        # A fresh app instance uses the same shared index and preserves decisions.
        restarted = create_app(settings, gateway=FakeGateway())
        with TestClient(restarted) as other:
            auth = other.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
            other.headers['X-CSRF-Token'] = auth['csrf_token']
            assert other.get('/api/system').json()['index_ready']
            assert other.get(f"/api/tickets/{ticket['id']}").json()['ticket']['status'] == 'open'
            assert other.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).json()['items']
            with Session(restarted.state.engine) as session:
                session.add(Job(id='other-instance', kind='reindex', status='running'))
                session.commit()
            assert other.post('/api/knowledge/reindex').status_code == 409
    finally:
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()
