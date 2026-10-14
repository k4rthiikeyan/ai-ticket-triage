import pytest
from sqlmodel import Session, select
from backend.app.config import Settings, DEMO_USERNAME, DEMO_PASSWORD
from backend.app.models import Admin
from backend.app.seed import seed


def enable_demo(workspace):
    app, client, _, _, settings = workspace
    settings.public_demo_enabled = True
    seed(app.state.engine, settings)
    return app, client, settings


def sign_in_demo(client):
    response = client.post('/api/auth/login', json={'username': DEMO_USERNAME, 'password': DEMO_PASSWORD})
    assert response.status_code == 200
    assert response.json()['is_demo']
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']


def test_demo_is_opt_in_and_never_publishes_admin_password(workspace):
    assert workspace[1].get('/api/auth/demo').json() == {'enabled': False}
    assert workspace[1].post('/api/auth/login', json={'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}).status_code == 401
    app, client, settings = enable_demo(workspace)
    credentials = client.get('/api/auth/demo')
    assert credentials.json() == {'enabled': True, 'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}
    assert settings.admin_password not in credentials.text
    seed(app.state.engine, settings)
    with Session(app.state.engine) as session:
        assert len(session.exec(select(Admin).where(Admin.username == DEMO_USERNAME)).all()) == 1


def test_demo_can_try_workspace_but_cannot_change_operator_settings(workspace):
    _, client, settings = enable_demo(workspace)
    sign_in_demo(client)
    assert client.get('/api/auth/me').json()['is_demo']
    assert client.post('/api/tickets', json={'subject': 'Visitor example request', 'body': 'An example request entered by a demo visitor.'}).status_code == 201
    assert client.post('/api/articles', json={'title': 'Visitor example guidance', 'body': 'Guidance entered by a visitor for an example support workflow.'}).status_code == 201
    for method, path, body in [
        ('POST', '/api/queues', {'name': 'Visitor queue'}),
        ('PATCH', '/api/queues/1', {'name': 'Visitor queue'}),
        ('POST', '/api/categories', {'name': 'Visitor category', 'queue_id': 1}),
        ('PATCH', '/api/categories/1', {'name': 'Visitor category', 'queue_id': 1}),
        ('POST', '/api/system/check-provider?kind=embeddings', None),
    ]:
        assert client.request(method, path, json=body).status_code == 403
    # Disabling public access also invalidates existing demo sessions.
    settings.public_demo_enabled = False
    assert client.get('/api/tickets').status_code == 401
    assert client.post('/api/auth/login', json={'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}).status_code == 401
    assert client.get('/api/auth/demo').json() == {'enabled': False}
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-password'})
    assert login.status_code == 200 and not login.json()['is_demo']
    client.headers['X-CSRF-Token'] = login.json()['csrf_token']
    assert client.post('/api/queues', json={'name': 'Administrator queue'}).status_code == 201


def test_demo_username_cannot_be_the_administrator():
    with pytest.raises(ValueError, match='reserved'):
        Settings(admin_username=DEMO_USERNAME, _env_file=None)
