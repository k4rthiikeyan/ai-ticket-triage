"""Verify an upgrade on an explicitly selected disposable Neon branch, never main."""
import hashlib
import json
import os
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.db import make_engine, migrate
from backend.app.main import create_app
from backend.app.models import Workspace
from tests.conftest import FakeGateway
from tests.test_workspaces import visitor, add_knowledge


def main():
    url = os.environ['MIGRATION_TEST_URL']
    expected = os.environ['MIGRATION_TEST_HOST']
    assert make_url(url).host == expected and '-pooler' not in expected
    assert os.environ['MIGRATION_TEST_BRANCH'].startswith('br-')
    settings = Settings(database_url=url, admin_password='unused-on-existing-database', public_demo_enabled=True, _env_file=None)
    engine = make_engine(settings)

    def content_digest():
        with engine.connect() as connection:
            content = {}
            for table, fields in [('ticket', 'id, subject, body, status'), ('article', 'id, title, body, revision'),
                                  ('decision', 'id, ticket_id, action'), ('recommendationrun', 'id, ticket_id, payload')]:
                content[table] = [tuple(row) for row in connection.execute(text(f'SELECT {fields} FROM {table} ORDER BY id'))]
        return hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest(), {k: len(v) for k, v in content.items()}

    before, counts = content_digest()
    print('Disposable branch connected; testing populated schema upgrade.', flush=True)
    migrate(engine)
    assert content_digest()[0] == before
    print('Owner content preserved; exercising isolated visitors.', flush=True)
    migrate(engine)
    assert content_digest()[0] == before
    app = create_app(settings, gateway=FakeGateway())
    with TestClient(app):
        first, second = visitor(app), visitor(app)
        add_knowledge(first)
        job = first.post('/api/knowledge/reindex').json()
        assert job['status'] == 'succeeded', job
        assert first.post('/api/knowledge/search', json={'query': 'Duplicate charge'}).json()['items']
        ticket = first.post('/api/tickets', json={'subject': 'Branch upgrade verification', 'body': 'A duplicate charge appeared but the product still works.'}).json()
        run_job = first.post(f"/api/tickets/{ticket['id']}/triage").json()
        assert run_job['status'] == 'succeeded', run_job
        run = first.get(f"/api/tickets/{ticket['id']}").json()['runs'][0]
        assert first.post(f"/api/tickets/{ticket['id']}/decisions", json={'expected_revision': 1,
            'recommendation_id': run['id'], **run['payload']['suggestions']}).status_code == 201
        assert second.get(f"/api/tickets/{ticket['id']}").status_code == 404
        assert second.get('/api/jobs/' + run_job['id']).status_code == 404
        assert second.get('/api/articles').json() == []
        assert second.get('/api/dashboard').json()['total'] == 0
    print(json.dumps({'migration': 'passed twice', 'owner_records_preserved': counts,
                      'postgres_rag_with_mock_provider': 'passed', 'visitor_isolation': 'passed'}))
    engine.dispose()


if __name__ == '__main__':
    main()
