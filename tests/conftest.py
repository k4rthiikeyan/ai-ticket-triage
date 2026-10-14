import json
import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


class FakeGateway:
    failure = None
    raw = None

    def status(self):
        return {'available': True, 'message': 'Mocked OpenRouter for tests'}

    def embed(self, texts):
        if self.failure:
            raise self.failure
        return [[1.0, 0.0, 0.0] for _ in texts]

    def generate(self, messages, schema):
        if self.failure:
            raise self.failure
        if self.raw is not None:
            return self.raw
        data = json.loads(messages[-1]['content'])
        article, policy = data['sources'][0], data['sources'][-1]
        return json.dumps({'abstain': False, 'category_id': data['taxonomy'][0]['category_id'], 'priority': 'normal',
                           'category_rationale': 'The request concerns a billing charge.', 'priority_rationale': 'The product is working normally.',
                           'category_evidence': [{'chunk_id': article['chunk_id'], 'quote': 'Duplicate charges belong to Billing.'}],
                           'priority_evidence': [{'chunk_id': policy['chunk_id'], 'quote': 'Routine billing requests have normal priority.'}]})


class FakeStore:
    failure = False
    similarity = .82

    def build(self, articles, gateway, progress):
        if self.failure:
            raise ValueError('Embedding rebuild failed')
        gateway.embed(['check connectivity'])
        progress('Embedding test knowledge')
        return 'kb_' + uuid4().hex, len(articles)

    def retrieve(self, index_id, vector, top_k=4):
        return [{'chunk_id': 'billing-refunds:v1:0', 'article_id': 'billing-refunds', 'article_revision': 1,
                 'title': 'Duplicate charges', 'text': 'Duplicate charges belong to Billing.', 'similarity': self.similarity}], [
                {'chunk_id': 'urgency-rubric:v1:0', 'article_id': 'urgency-rubric', 'article_revision': 1,
                 'title': 'Urgency policy', 'text': 'Routine billing requests have normal priority.', 'similarity': .6}]


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(database_url=f'sqlite:///{(tmp_path / "test.db").as_posix()}',
                        admin_password='test-password', _env_file=None)
    gateway, store = FakeGateway(), FakeStore()
    app = create_app(settings, gateway, store)
    with TestClient(app) as client:
        yield app, client, gateway, store, settings


@pytest.fixture
def signed(workspace):
    app, client, *_ = workspace
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'})
    assert response.status_code == 200
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    for article in [
        {'title': 'Test billing guidance', 'body': 'Duplicate charges belong to Billing. Investigate the payment request.'},
        {'title': 'Test urgency policy', 'body': 'Routine billing requests have normal priority.', 'is_policy': True},
    ]:
        assert client.post('/api/articles', json=article).status_code == 201
    return workspace


def wait_job(client, app, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get('/api/jobs/' + job_id).json()
        if job['status'] not in ['queued', 'running'] and not app.state.busy:
            return job
        time.sleep(.01)
    raise AssertionError('Background job did not finish')


def create_ticket(client, subject='Duplicate charge', body='A duplicate charge appeared on my subscription. Everything still works.'):
    response = client.post('/api/tickets', json={'subject': subject, 'body': body})
    assert response.status_code == 201, response.text
    return response.json()


def triage(client, app, ticket_id, method='rules'):
    response = client.post(f'/api/tickets/{ticket_id}/triage?method={method}')
    assert response.status_code == 202, response.text
    job = wait_job(client, app, response.json()['id'])
    detail = client.get(f'/api/tickets/{ticket_id}').json()
    return job, next(r for r in detail['runs'] if r['id'] == job['result']['recommendation_id'])


def reindex(client, app):
    response = client.post('/api/knowledge/reindex')
    assert response.status_code == 202, response.text
    return wait_job(client, app, response.json()['id'])
