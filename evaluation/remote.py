"""Opt-in live evaluation through the deployed public demo's normal API."""
import argparse
import json
from pathlib import Path
import httpx
from .run import ROOT, summarize


def evaluate(base_url):
    cases = [c for c in json.loads((ROOT / 'cases.json').read_text()) if c['id'] in {'b2', 'edge-negation', 'edge-unknown'}]
    rows = []
    with httpx.Client(base_url=base_url.rstrip('/') + '/api/', timeout=290) as client:
        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        def post(path, body=None):
            response = client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        access = get('auth/demo')
        assert access['enabled'], 'Public demo is disabled'
        auth = post('auth/login', {'username': access['username'], 'password': access['password']})
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        assert auth['is_demo'] and get('tickets')['total'] == 0
        system = get('system')
        assert all(system[key].endswith(':free') for key in ['embedding_model', 'generation_model'])
        taxonomy = get('taxonomy')['categories']
        labels = {c['id']: c['slug'] for c in taxonomy}
        fixture_ids, bodies = {}, {}
        for fixture in json.loads((ROOT / 'knowledge.json').read_text()):
            article = post('articles', {'title': 'Evaluation fixture — ' + fixture['title'], 'body': fixture['body'], 'is_policy': fixture.get('is_policy', False)})
            fixture_ids[article['id']], bodies[article['id']] = fixture['id'], fixture['body']
        index_job = post('knowledge/reindex')
        assert index_job['status'] == 'succeeded', index_job.get('error')
        for case in cases:
            ticket = post('tickets', {'subject': 'Evaluation fixture — ' + case['subject'], 'body': case['body']})
            job = post(f"tickets/{ticket['id']}/triage")
            detail = get(f"tickets/{ticket['id']}")
            run = detail['runs'][0]
            result = run['payload']
            suggestion = result.get('suggestions') or {}
            expected = case['category']
            row = {'id': case['id'], 'ticket_id': ticket['id'], 'expected_category': expected, 'expected_priority': case['priority'],
                   'predicted_category': labels.get(suggestion.get('category_id')), 'predicted_priority': suggestion.get('priority'),
                   'outcome': run['outcome'], 'latency_ms': result.get('latency_ms', 0),
                   'category_correct': labels.get(suggestion.get('category_id')) == expected,
                   'priority_correct': suggestion.get('priority') == case['priority'],
                   'review_correct': expected is not None or run['outcome'] == 'needs_review',
                   'retrieval_hit_at_4': None if expected is None else any(fixture_ids.get(s['article_id']) == 'eval-' + expected for s in result.get('retrieved', [])),
                   'quotes_exact': all(c['quote'] in bodies[c['article_id']] for c in result.get('citations', [])) if result.get('citations') else None,
                   'error': job.get('error')}
            if run['outcome'] == 'suggested':
                decision = post(f"tickets/{ticket['id']}/decisions", {'expected_revision': 1,
                    'recommendation_id': run['id'], **suggestion, 'note': 'Evaluation fixture: accepted after checking cited source text.'})
                row['persisted_after_confirmation'] = decision['action'] == 'accepted' and get(f"tickets/{ticket['id']}")['ticket']['status'] == 'open'
            rows.append(row)
        post('auth/logout')
    return {'mode': 'live_free_rag_deployed', 'models': {key: system[key] for key in ['embedding_model', 'generation_model']},
            'limitations': 'Three hand-authored smoke cases, not a production accuracy estimate. Created in a separate demo workspace, which expires automatically. Provider errors are reported as failures.',
            'metrics': summarize(rows), 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.url.startswith('https://'), 'Use the HTTPS deployment URL'
    report = evaluate(args.url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['metrics'], indent=2))


if __name__ == '__main__':
    main()
