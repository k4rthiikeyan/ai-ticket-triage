"""Opt-in real-provider resolution smoke test in a disposable local database."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def run():
    # Never connect to the configured owner database or write its knowledge.
    Path('artifacts').mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='resolution-live-', dir='artifacts') as folder:
        settings = Settings(database_url='sqlite:///' + (Path(folder) / 'evaluation.db').resolve().as_posix(),
            admin_password='local-evaluation-only', public_demo_enabled=False, cookie_secure=False, auto_migrate=True)
        with TestClient(create_app(settings)) as admin:
            login = admin.post('/api/auth/login', json={'username': settings.admin_username, 'password':'local-evaluation-only'})
            login.raise_for_status()
            admin.headers['X-CSRF-Token'] = login.json()['csrf_token']
            for article in [
                {'title':'Example refund timing', 'body':'Refund policy for this fictional example product: An approved refund can take five to ten business days to reach the original payment method. Billing handles refund questions. Do not promise that a payment has been processed or inspect account-specific payment status.'},
                {'title':'Example urgency policy','body':'Routine billing-policy questions have normal priority. Security incidents and service outages affecting all users are urgent. An issue blocking work without a workaround has high priority. Optional future features have low priority.','is_policy':True},
            ]:
                admin.post('/api/articles',json=article).raise_for_status()
            index = admin.post('/api/knowledge/reindex')
            index.raise_for_status()
            if index.json()['status'] != 'succeeded':
                return {'mode':'live_free_resolution','passed':False,'index_error':index.json().get('error')}
            with TestClient(admin.app) as customer:
                session=customer.post('/api/portal/session');session.raise_for_status()
                customer.headers['X-Customer-CSRF']=session.json()['csrf_token']
                rows=[]
                for subject,body,expected in [
                    ('Refund timing','How long does an approved refund usually take to reach the original payment method?','resolved_ai'),
                    ('Refund approval','Please issue a refund for my payment.','needs_review'),
                    ('Human assistance','Please connect me to a human agent.','needs_review'),
                ]:
                    response=customer.post('/api/portal/tickets',json={'subject':subject,'body':body});response.raise_for_status()
                    data=response.json();ticket=data['ticket']
                    rows.append({'subject':subject,'expected':expected,'actual':ticket['resolution_state'],
                        'answer':ticket['answer'],'sources_exact':all(c['quote'] in c['text'] for m in data['messages'] for c in m['citations']),
                        'has_answer_evidence':any(m['citations'] for m in data['messages']),'passed':ticket['resolution_state']==expected})
                return {'mode':'live_free_resolution','embedding_model':settings.embedding_model,
                    'generation_model':settings.generation_model,'limitations':'Three synthetic smoke cases; one automatic answer and two no-provider escalation gates. Not an accuracy estimate.',
                    'passed':all(r['passed'] for r in rows),'results':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True,help='Explicitly allow up to three free provider requests: indexing, query embedding, answer generation.')
    parser.add_argument('--output',type=Path,default=Path('artifacts/live-resolution.json'))
    args=parser.parse_args()
    report=run()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
