"""Opt-in live customer/admin verification in an isolated deployed demo workspace."""
import argparse
import json
from pathlib import Path
import httpx


def evaluate(base_url):
    report = {'mode':'live_deployed_resolution', 'passed':False, 'checks':{}}
    checks = report['checks']
    with httpx.Client(base_url=base_url.rstrip('/')+'/api/', timeout=290) as client:
        def get(path):
            response=client.get(path);response.raise_for_status();return response.json()
        def post(path,body=None):
            response=client.post(path,json=body);response.raise_for_status();return response.json()
        access=get('auth/demo')
        assert access['enabled'], 'The public demo is disabled.'
        auth=post('auth/login',{'username':access['username'],'password':access['password']})
        assert auth['is_demo']
        client.headers['X-CSRF-Token']=auth['csrf_token']
        try:
            articles=get('articles')
            bodies={a['id']:a['body'] for a in articles}
            system=get('system')
            report['models']={key:system[key] for key in ['embedding_model','generation_model']}
            assert all(model.endswith(':free') for model in report['models'].values())
            index=post('knowledge/reindex')
            assert index['status']=='succeeded', index.get('error')
            checks['index_rebuilt']=True
            identity=post('portal/session')
            assert identity['is_demo']
            client.headers['X-Customer-CSRF']=identity['csrf_token']
            enquiry=post('portal/tickets',{'subject':'Live verification — refund timing policy',
                'body':'What is the documented general time range for an approved refund to reach the original payment method? I only need the general policy, not an account lookup.'})
            ticket=enquiry['ticket'];identifier=ticket['id']
            assert ticket['resolution_state']=='resolved_ai', get(f'tickets/{identifier}')['runs'][0]['payload']
            citations=[c for m in enquiry['messages'] for c in m['citations']]
            assert citations and all(c['quote'] in bodies[c['article_id']] for c in citations)
            assert ticket['answer'].strip() and ticket['status']=='resolved'
            checks['automatic_answer']={'answer':ticket['answer'],'state':ticket['resolution_state'],
                'source_count':len(citations),'quotes_exact':True}
            unchanged=ticket['answer']
            initial_budget=get('system')['demo_limits']['ai_remaining_today']
            for label,body,reason in [
                ('human_request','Please connect me to a human agent about this enquiry.','human_requested'),
                ('financial_action','Please issue a refund for my payment.','action_required'),
                ('security_incident','My account was hacked. Please investigate this fictional example.','security'),
                ('service_incident','The service is down for all users in this fictional example.','outage'),
                ('privacy_request','Please delete my personal data in this fictional example.','privacy_legal')]:
                result=post('portal/tickets',{'subject':'Live verification — '+label,'body':body})
                assert result['ticket']['resolution_state']=='needs_review' and not result['ticket']['answer']
                detail=get(f"tickets/{result['ticket']['id']}")
                assert detail['ticket']['review_reason']==reason
                checks[label]={'state':result['ticket']['resolution_state'],'reason':reason}
            assert get('system')['demo_limits']['ai_remaining_today']==initial_budget
            checks['risk_gates_used_no_provider_requests']=True
            reviewed=post(f'tickets/{identifier}/review',{'action':'request_changes','expected_version':ticket['outcome_version'],
                'body':'INTERNAL REVIEW NOTE: Keep the documented refund time range and write one concise customer-facing sentence.'})
            revision=post(f'tickets/{identifier}/resolve')
            assert revision['status']=='succeeded',revision.get('error')
            draft=get(f'tickets/{identifier}')['ticket']
            assert draft['draft_run_id'] and draft['resolution_state']=='changes_requested'
            public=get(f'portal/tickets/{identifier}')
            assert public['ticket']['answer']==unchanged and 'INTERNAL REVIEW NOTE' not in json.dumps(public)
            checks['revision_private_until_approved']=True
            post(f'tickets/{identifier}/review',{'action':'approve','expected_version':draft['outcome_version']})
            public=get(f'portal/tickets/{identifier}')
            assert public['ticket']['resolution_state']=='resolved_human' and public['messages'][-1]['kind']=='revised_answer'
            assert 'INTERNAL REVIEW NOTE' not in json.dumps(public)
            checks['revised_answer_published']=True
            post(f'tickets/{identifier}/review',{'action':'correct','expected_version':public['ticket']['outcome_version'],
                'body':'Our support team reviewed this answer: an approved refund can take five to ten business days to reach the original payment method.'})
            corrected=get(f'portal/tickets/{identifier}')
            assert corrected['messages'][-1]['kind']=='correction'
            assert sum(m['kind'] in ['answer','revised_answer','correction'] for m in corrected['messages'])==3
            checks['correction_visible_and_history_preserved']=True
            reopened=post(f'portal/tickets/{identifier}/followup',{'expected_version':corrected['ticket']['outcome_version'],
                'body':'The answer did not resolve my enquiry. Please have a person review the next steps.'})
            assert reopened['ticket']['resolution_state']=='needs_review'
            assert any(t['id']==identifier for t in get('tickets?resolution=review')['items'])
            checks['customer_reopen_in_admin_queue']=True
            with httpx.Client(base_url=base_url.rstrip('/')+'/api/',timeout=30) as stranger:
                response=stranger.post('portal/session');response.raise_for_status()
                assert stranger.get(f'portal/tickets/{identifier}').status_code==404
                assert stranger.get('tickets').status_code==401
            checks['customer_isolation_and_admin_auth']=True
            report['ai_requests_used']=system['demo_limits']['ai_remaining_today']-get('system')['demo_limits']['ai_remaining_today']
        finally:
            post('auth/logout')
            assert client.get('auth/me').status_code==401
            assert client.get('portal/tickets').status_code==401
            checks['demo_ended_and_sessions_revoked']=True
    report['passed']=True
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert args.url.startswith('https://')
    report=evaluate(args.url)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
