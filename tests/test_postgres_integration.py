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
from .test_workspaces import visitor, add_knowledge
from backend.app.seed import seed


@pytest.mark.skipif(not os.environ.get('TEST_POSTGRES_URL'), reason='Disposable Postgres service is not configured')
def test_full_workflow_and_restart_with_real_postgres():
    base = os.environ['TEST_POSTGRES_URL']
    schema = 'triage_test_' + uuid4().hex
    control = make_engine(Settings(database_url=base, _env_file=None))
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    url = make_url(base).update_query_dict({'options': f'-csearch_path={schema}'})
    settings = Settings(database_url=url.render_as_string(hide_password=False), admin_password='test-password', ai_minute_limit=20, _env_file=None)
    try:
        # Verify the additive release migration against populated prior-schema data.
        from pathlib import Path
        from alembic import command
        from alembic.config import Config
        legacy = make_engine(settings)
        config = Config(str(Path(__file__).resolve().parents[1] / 'backend' / 'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'backend' / 'migrations'))
        with legacy.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, '0003')
            legacy_id = connection.execute(text("INSERT INTO ticket (workspace_id, subject, body, original_subject, original_body, revision, status, created_at, updated_at) VALUES (1, 'Preserved migration fixture', 'Existing support content must survive.', 'Preserved migration fixture', 'Existing support content must survive.', 1, 'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id")).scalar_one()
        legacy.dispose()
        app = create_app(settings, gateway=FakeGateway())
        with TestClient(app) as client:
            auth = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
            client.headers['X-CSRF-Token'] = auth['csrf_token']
            preserved = client.get(f'/api/tickets/{legacy_id}').json()['ticket']
            assert preserved['body'] == 'Existing support content must survive.'
            assert preserved['resolution_state'] == 'unprocessed' and preserved['outcome_version'] == 0
            assert client.get('/api/articles').json() == []
            created_queue = client.post('/api/queues', json={'name': 'User entered queue'})
            assert created_queue.status_code == 201, created_queue.text
            assert created_queue.json()['id'] > 3
            for article in [
                {'title': 'Billing guidance', 'body': 'Duplicate charges belong to Billing. Review the payment request. An approved refund can take five to ten business days.'},
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
            customer = TestClient(app)
            customer_session = customer.post('/api/portal/session')
            assert customer_session.status_code == 200
            customer.headers['X-Customer-CSRF'] = customer_session.json()['csrf_token']
            enquiry = customer.post('/api/portal/tickets', json={
                'subject': 'Refund policy timing', 'body': 'How long does an approved refund normally take?'
            })
            assert enquiry.status_code == 201, enquiry.text
            answered = enquiry.json()['ticket']
            assert answered['resolution_state'] == 'resolved_ai'
            assert enquiry.json()['messages'][-1]['citations']
            reopened = customer.post(f"/api/portal/tickets/{answered['id']}/followup", json={
                'body': 'I need someone to check this answer.', 'expected_version': answered['outcome_version']
            })
            assert reopened.status_code == 200, reopened.text
            correction = client.post(f"/api/tickets/{answered['id']}/review", json={
                'action': 'correct', 'expected_version': reopened.json()['ticket']['outcome_version'],
                'body': 'Our team reviewed this enquiry. Approved refunds take five to ten business days.'
            })
            assert correction.status_code == 200, correction.text
        # A fresh app instance uses the same shared index and preserves decisions.
        restarted = create_app(settings, gateway=FakeGateway())
        with TestClient(restarted) as other:
            auth = other.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'}).json()
            other.headers['X-CSRF-Token'] = auth['csrf_token']
            assert other.get('/api/system').json()['index_ready']
            assert other.get(f"/api/tickets/{ticket['id']}").json()['ticket']['status'] == 'open'
            restored_customer = TestClient(restarted, cookies=customer.cookies)
            restored_answer = restored_customer.get(f"/api/portal/tickets/{answered['id']}")
            assert restored_answer.status_code == 200, restored_answer.text
            assert restored_answer.json()['ticket']['resolution_state'] == 'resolved_human'
            assert restored_answer.json()['messages'][-1]['kind'] == 'correction'
            assert other.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).json()['items']
            settings.public_demo_enabled = True
            seed(restarted.state.engine, settings)
            first, second = visitor(restarted), visitor(restarted)
            add_knowledge(first)
            assert first.post('/api/knowledge/reindex').json()['status'] == 'succeeded'
            visitor_ticket = first.post('/api/tickets', json={'subject': 'Visitor duplicate charge', 'body': 'A duplicate charge appeared but everything still works.'}).json()
            visitor_job = first.post(f"/api/tickets/{visitor_ticket['id']}/triage").json()
            assert visitor_job['status'] == 'succeeded', visitor_job
            assert second.get(f"/api/tickets/{visitor_ticket['id']}").status_code == 404
            assert second.get('/api/jobs/' + visitor_job['id']).status_code == 404
            assert second.get('/api/articles').json() == []
            assert not second.get('/api/system').json()['index_ready']
            assert first.post('/api/auth/logout').status_code == 200
            assert first.get('/api/auth/me').status_code == 401
            assert other.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).json()['items']
            with Session(restarted.state.engine) as session:
                session.add(Job(id='other-instance', kind='reindex', status='running'))
                session.commit()
            assert other.post('/api/knowledge/reindex').status_code == 409
    finally:
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        control.dispose()
