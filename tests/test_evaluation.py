import json
from pathlib import Path
from evaluation.run import summarize


def test_evaluation_covers_taxonomy_and_reports_abstentions_as_misses():
    cases = json.loads((Path('evaluation') / 'cases.json').read_text())
    assert len(cases) == 24 and len({c['id'] for c in cases}) == 24
    assert len({c['category'] for c in cases if c['category']}) == 5
    assert {c['priority'] for c in cases if c['priority']} == {'normal', 'low', 'high', 'urgent'}
    report = summarize([
        {'id': 'labelled', 'expected_category': 'billing', 'category_correct': False, 'priority_correct': False,
         'review_correct': True, 'outcome': 'needs_review', 'latency_ms': 10},
        {'id': 'unrelated', 'expected_category': None, 'category_correct': True, 'priority_correct': True,
         'review_correct': True, 'outcome': 'needs_review', 'latency_ms': 20},
    ])
    assert report['category_accuracy'] == 0 and report['priority_accuracy'] == 0
    assert report['review_accuracy'] == 1 and report['suggestion_coverage'] == 0
