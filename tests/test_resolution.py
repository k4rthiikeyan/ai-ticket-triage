"""Autonomous answers, exception gates, customer ownership and human correction."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.models import Ticket, AppState, TicketMessage
from backend.app.services.resolution import risk_reason
from tests.conftest import reindex


def answer_raw():
    return json.dumps({
        'abstain': False, 'category_id': 1, 'priority': 'normal',
        'category_rationale': 'A routine billing question.', 'priority_rationale': 'An informational enquiry.',
        'category_evidence': [{'chunk_id': 'billing-refunds:v1:0', 'quote': 'Duplicate charges belong to Billing.'}],
        'priority_evidence': [{'chunk_id': 'urgency-rubric:v1:0', 'quote': 'Routine billing requests have normal priority.'}],
        'requires_human': False, 'reason_code': 'none',
        'answer': 'An approved refund can take five to ten business days to reach your original payment method.',
        'answer_evidence': [{'chunk_id': 'billing-refunds:v1:0', 'quote': 'An approved refund can take five to ten business days.'}],
    })


@pytest.fixture
def resolution_workspace(signed):
    app, admin, gateway, store, settings = signed
    original = store.retrieve
    def retrieve(*args, **kwargs):
        articles, policies = original(*args, **kwargs)
        articles[0]['text'] += ' An approved refund can take five to ten business days.'
        return articles, policies
    store.retrieve = retrieve
    gateway.raw = answer_raw()
    reindex(admin, app)
    return signed


def customer_client(app):
    client = TestClient(app)
    response = client.post('/api/portal/session')
    assert response.status_code == 200, response.text
    client.headers['X-Customer-CSRF'] = response.json()['csrf_token']
    return client


def submit(client, subject='Refund timing', body='How long does an approved refund usually take?'):
    response = client.post('/api/portal/tickets', json={'subject': subject, 'body': body})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize('message,reason', [
    ('Please connect me to a human agent', 'human_requested'),
    ('My account was hacked', 'security'),
    ('I lost my MFA authenticator', 'security'),
    ('Please issue a refund for my payment', 'action_required'),
    ('Please investigate my refund reference', 'action_required'),
    ('Delete my personal data', 'privacy_legal'),
    ('The service is down for all users', 'outage'),
    ('How long do approved refunds take?', None),
    ('How do I reset my password?', None),
    ('What is an outage?', None),
    ('How do I request a refund?', None),
    ('There is no account compromise or service outage. How long do refunds take?', None),
])
def test_risk_boundary(message, reason):
    assert risk_reason(message) == reason


def test_routine_answer_completes_without_admin_and_has_public_sources(resolution_workspace):
    app, admin, *_ = resolution_workspace
    customer = customer_client(app)
    data = submit(customer)
    ticket = data['ticket']
    assert ticket['status'] == 'resolved' and ticket['resolution_state'] == 'resolved_ai'
    assert 'five to ten' in ticket['answer']
    assert len(data['messages'][-1]['citations']) == 1
    assert not {'customer_id', 'review_note', 'draft_run_id', 'review_reason'} & ticket.keys()
    detail = admin.get(f"/api/tickets/{ticket['id']}").json()
    assert detail['decisions'][0]['action'] == 'automated'
    assert admin.get('/api/dashboard').json()['automation']['resolved_ai'] == 1


def test_customer_cannot_read_another_customer_or_admin(resolution_workspace):
    app, *_ = resolution_workspace
    one, two = customer_client(app), customer_client(app)
    ticket = submit(one)['ticket']
    assert two.get(f"/api/portal/tickets/{ticket['id']}").status_code == 404
    assert two.post(f"/api/portal/tickets/{ticket['id']}/followup", json={'body':'Help please', 'expected_version':ticket['outcome_version']}).status_code == 404
    assert two.get('/api/portal/tickets').json() == []
    assert one.get('/api/tickets').status_code == 401
    assert one.get('/api/system').status_code == 401
    one.headers.pop('X-Customer-CSRF')
    assert one.post('/api/portal/tickets', json={'subject':'Question', 'body':'A valid customer question'}).status_code == 403


@pytest.mark.parametrize('body,reason', [('Please refund my payment now.', 'action_required'), ('I want to speak to a human agent.', 'human_requested')])
def test_high_risk_never_calls_model(resolution_workspace, body, reason):
    app, admin, gateway, *_ = resolution_workspace
    gateway.failure = AssertionError('No provider call should happen for an explicit exception')
    data = submit(customer_client(app), 'Help needed', body)
    assert data['ticket']['resolution_state'] == 'needs_review'
    assert data['ticket']['answer'] == ''
    detail = admin.get(f"/api/tickets/{data['ticket']['id']}").json()
    assert detail['ticket']['review_reason'] == reason


@pytest.mark.parametrize('failure', ['provider', 'invalid_quote', 'low_retrieval', 'stale_index', 'malformed'])
def test_failures_preserve_enquiry_and_escalate(resolution_workspace, failure):
    app, admin, gateway, store, *_ = resolution_workspace
    if failure == 'provider': gateway.failure = ConnectionError('offline')
    if failure == 'invalid_quote':
        raw = json.loads(answer_raw()); raw['answer_evidence'][0]['quote'] = 'A made-up source'; gateway.raw = json.dumps(raw)
    if failure == 'low_retrieval': store.similarity = .1
    if failure == 'stale_index':
        with Session(app.state.engine) as db:
            state=db.get(AppState,1);state.knowledge_version+=1;db.add(state);db.commit()
    if failure == 'malformed': gateway.raw = '{"answer":"unsupported"}'
    data = submit(customer_client(app))
    assert data['ticket']['resolution_state'] == 'needs_review'
    assert data['ticket']['answer'] == ''
    assert admin.get('/api/tickets?resolution=review').json()['total'] == 1


def test_followup_reopens_and_admin_can_publish_correction(resolution_workspace):
    app, admin, *_ = resolution_workspace
    customer=customer_client(app)
    ticket=submit(customer)['ticket']
    path=f"/api/portal/tickets/{ticket['id']}/followup"
    reopened=customer.post(path,json={'body':'That did not help, please investigate.', 'expected_version':ticket['outcome_version']}).json()['ticket']
    assert reopened['resolution_state']=='needs_review'
    assert customer.post(path,json={'body':'Another message', 'expected_version':ticket['outcome_version']}).status_code==409
    review=f"/api/tickets/{ticket['id']}/review"
    assert admin.post(review,json={'action':'correct','expected_version':reopened['outcome_version'],'body':'We have reviewed your request. Please use the documented support channel for payment investigation.'}).status_code==200
    detail=customer.get(f"/api/portal/tickets/{ticket['id']}").json()
    assert detail['ticket']['resolution_state']=='resolved_human'
    assert detail['messages'][-1]['kind']=='correction'
    assert len([m for m in detail['messages'] if m['kind'] in ['answer','correction']])==2


def test_admin_revision_is_private_until_published_and_version_checked(resolution_workspace):
    app, admin, gateway, *_ = resolution_workspace
    customer=customer_client(app);ticket=submit(customer)['ticket'];base=f"/api/tickets/{ticket['id']}"
    review=admin.post(base+'/review',json={'action':'request_changes','expected_version':ticket['outcome_version'],'body':'Internal instruction: make this more concise.'})
    assert review.status_code==200
    raw=json.loads(answer_raw());raw['answer']='Refunds can take five to ten business days.';gateway.raw=json.dumps(raw)
    job=admin.post(base+'/resolve');assert job.status_code==202
    current=admin.get(base).json()['ticket']
    assert current['draft_run_id'] and current['resolution_state']=='changes_requested'
    public=customer.get(f"/api/portal/tickets/{ticket['id']}").json()
    assert public['ticket']['answer']==ticket['answer']
    assert 'Internal instruction' not in json.dumps(public)
    assert admin.post(base+'/review',json={'action':'approve','expected_version':ticket['outcome_version']}).status_code==409
    assert admin.post(base+'/review',json={'action':'approve','expected_version':current['outcome_version']}).status_code==200
    public=customer.get(f"/api/portal/tickets/{ticket['id']}").json()
    assert public['ticket']['answer']==raw['answer'] and public['messages'][-1]['kind']=='revised_answer'


def test_inflight_answer_cannot_overwrite_human_correction(resolution_workspace):
    app, admin, gateway, *_ = resolution_workspace
    original_generate=gateway.generate
    def generate(messages,schema):
        with Session(app.state.engine) as db:
            ticket=db.exec(select(Ticket).where(Ticket.customer_id != None)).one()
            ticket.outcome_version+=1;ticket.resolution_state='resolved_human';ticket.status='resolved';ticket.answer='Human intervention wins.'
            db.add(ticket);db.add(TicketMessage(ticket_id=ticket.id,author='admin',kind='correction',body=ticket.answer));db.commit()
        return original_generate(messages,schema)
    gateway.generate=generate
    ticket=submit(customer_client(app))['ticket']
    assert ticket['resolution_state']=='resolved_human' and ticket['answer']=='Human intervention wins.'


def test_inflight_knowledge_edit_prevents_publication(resolution_workspace):
    app, admin, gateway, *_ = resolution_workspace
    original=gateway.generate
    def generate(messages,schema):
        with Session(app.state.engine) as db:
            state=db.get(AppState,1);state.knowledge_version+=1;db.add(state);db.commit()
        return original(messages,schema)
    gateway.generate=generate
    ticket=submit(customer_client(app))['ticket']
    assert ticket['resolution_state']=='needs_review' and ticket['answer']==''


def test_exhausted_budget_keeps_ticket_for_admin(resolution_workspace):
    app, admin, gateway, store, settings = resolution_workspace
    settings.ai_daily_limit=1  # The fixture already spent one request on indexing.
    gateway.failure=AssertionError('An exhausted budget must not call the provider')
    ticket=submit(customer_client(app))['ticket']
    assert ticket['resolution_state']=='needs_review'
    detail=admin.get(f"/api/tickets/{ticket['id']}").json()
    assert 'limit' in detail['runs'][0]['payload']['error']


def test_customer_session_expiry_does_not_delete_owner_enquiry(resolution_workspace):
    from datetime import timedelta
    from backend.app.models import CustomerSession, now
    app, admin, *_=resolution_workspace
    customer=customer_client(app);ticket=submit(customer)['ticket']
    with Session(app.state.engine) as db:
        identity=db.exec(select(CustomerSession)).one();identity.expires_at=now()-timedelta(seconds=1);db.add(identity);db.commit()
    assert customer.get('/api/portal/tickets').status_code==401
    assert admin.get(f"/api/tickets/{ticket['id']}").status_code==200


def test_no_false_completion_via_legacy_status_endpoint(resolution_workspace):
    app, admin, *_=resolution_workspace
    ticket=submit(customer_client(app))['ticket']
    assert admin.patch(f"/api/tickets/{ticket['id']}",json={'expected_revision':1,'status':'resolved'}).status_code==422


def test_restart_recovers_interrupted_customer_answer(resolution_workspace):
    from datetime import timedelta
    from backend.app.models import Job, now
    from backend.app.main import create_app
    app, admin, gateway, store, settings=resolution_workspace
    customer=customer_client(app);ticket=submit(customer)['ticket']
    with Session(app.state.engine) as db:
        current=db.get(Ticket,ticket['id']);current.resolution_state='processing';current.outcome_version+=1;db.add(current)
        db.add(Job(id='stopped-resolution',workspace_id=1,ticket_id=current.id,kind='revise',status='running',
            result={'outcome_version':current.outcome_version},created_at=now()-timedelta(hours=1)))
        db.commit()
    with TestClient(create_app(settings,gateway,store)) as restarted:
        assert restarted.get('/api/health').status_code==200
        data=customer.get(f"/api/portal/tickets/{ticket['id']}").json()
        assert data['ticket']['resolution_state']=='needs_review'
        assert data['messages'][-1]['kind']=='handoff'


@pytest.mark.parametrize('old_request', [True, False])
def test_customer_read_recovers_overdue_work_without_restart(resolution_workspace, old_request):
    from datetime import timedelta
    from backend.app.models import Job, now
    app, admin, *_ = resolution_workspace
    customer = customer_client(app)
    ticket = submit(customer)['ticket']
    with Session(app.state.engine) as db:
        current = db.get(Ticket, ticket['id'])
        current.resolution_state = 'processing'
        current.outcome_version += 1
        db.add(current)
        db.add(Job(id='warm-instance-request', workspace_id=1, ticket_id=current.id,
                   kind='revise', status='running', result={'outcome_version':current.outcome_version},
                   created_at=now() - timedelta(hours=1) if old_request else now()))
        db.commit()
    detail = customer.get(f"/api/portal/tickets/{ticket['id']}").json()
    assert detail['ticket']['resolution_state'] == ('needs_review' if old_request else 'processing')
    if old_request:
        assert detail['messages'][-1]['kind'] == 'handoff'
        # Polling again must not append duplicate handoff notices.
        again = customer.get(f"/api/portal/tickets/{ticket['id']}").json()
        assert len(again['messages']) == len(detail['messages'])
    with Session(app.state.engine) as db:
        assert db.get(Job, 'warm-instance-request').status == ('failed' if old_request else 'running')


@pytest.mark.parametrize('mode',['model_requests_human','false_action_claim','policy_as_answer'])
def test_generated_answer_must_remain_within_its_authority(resolution_workspace,mode):
    app, admin, gateway, *_=resolution_workspace
    raw=json.loads(answer_raw())
    if mode=='model_requests_human':
        raw['requires_human']=True;raw['reason_code']='action_required'
    elif mode=='false_action_claim':
        raw['answer']='We have refunded your payment.'
    else:
        raw['answer_evidence']=[{'chunk_id':'urgency-rubric:v1:0','quote':'Routine billing requests have normal priority.'}]
    gateway.raw=json.dumps(raw)
    data=submit(customer_client(app))
    assert data['ticket']['resolution_state']=='needs_review' and data['ticket']['answer']==''
    assert not any(m['author']=='assistant' for m in data['messages'])


def test_demo_cleanup_removes_customer_sessions_and_public_conversation(resolution_workspace):
    from backend.app.seed import seed
    from backend.app.models import CustomerSession, Workspace
    app, admin, gateway, store, settings=resolution_workspace
    settings.public_demo_enabled=True
    seed(app.state.engine,settings)
    demo=TestClient(app)
    login=demo.post('/api/auth/login',json={'username':'demo','password':'try-triage'}).json()
    demo.headers['X-CSRF-Token']=login['csrf_token']
    identity=demo.post('/api/portal/session').json()
    assert identity['is_demo']
    demo.headers['X-Customer-CSRF']=identity['csrf_token']
    ticket=submit(demo,'Human support','Please connect me to a human agent.')['ticket']
    with Session(app.state.engine) as db:
        workspace=db.get(Ticket,ticket['id']).workspace_id
    assert admin.get(f"/api/tickets/{ticket['id']}").status_code==404
    assert demo.post('/api/auth/logout').status_code==200
    assert demo.get('/api/portal/tickets').status_code==401
    with Session(app.state.engine) as db:
        assert db.get(Workspace,workspace) is None
        assert db.exec(select(CustomerSession).where(CustomerSession.workspace_id==workspace)).first() is None
        assert db.exec(select(TicketMessage).where(TicketMessage.ticket_id==ticket['id'])).first() is None
