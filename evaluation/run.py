"""Reproducible rules benchmark; opt-in live free-model RAG in disposable SQLite."""
import argparse
import json
import statistics
import tempfile
from pathlib import Path
from types import SimpleNamespace
from sqlmodel import SQLModel
from backend.app.config import Settings
from backend.app.db import make_engine
from backend.app.models import Article, AppState, Category, Ticket
from backend.app.rag import OpenRouterGateway, VectorStore, run_rag, run_rules
from backend.app.seed import CATEGORY_SEEDS
from backend.app.services.usage import BudgetedGateway

ROOT = Path(__file__).parent


def summarize(rows):
    labelled = [r for r in rows if r['expected_category'] is not None]
    review = [r for r in rows if r['expected_category'] is None]
    return {'cases': len(rows), 'labelled_cases': len(labelled),
            'category_accuracy': sum(r['category_correct'] for r in labelled) / len(labelled) if labelled else None,
            'priority_accuracy': sum(r['priority_correct'] for r in labelled) / len(labelled) if labelled else None,
            'review_accuracy': sum(r['review_correct'] for r in review) / len(review) if review else None,
            'suggestion_coverage': sum(r['outcome'] == 'suggested' for r in rows) / len(rows),
            'median_latency_ms': statistics.median(r['latency_ms'] for r in rows),
            'failed_cases': [r['id'] for r in rows if not (r['category_correct'] and r['priority_correct'] and r['review_correct'])]}


def benchmark(live=False, limit=None):
    cases = json.loads((ROOT / 'cases.json').read_text())
    if limit:
        cases = cases[:limit]
    categories = [Category(id=i, slug=slug, name=name, queue_id=i, keywords=keywords)
                  for i, (slug, name, _, keywords) in enumerate(CATEGORY_SEEDS, 1)]
    labels = {c.id: c.slug for c in categories}
    settings = Settings()
    rows = []
    with tempfile.TemporaryDirectory(prefix='triage-evaluation-') as temporary:
        settings.database_url = 'sqlite:///' + (Path(temporary) / 'evaluation.db').as_posix()
        engine = make_engine(settings)
        SQLModel.metadata.create_all(engine)
        provider = OpenRouterGateway(settings) if live else None
        try:
            if live:
                app = SimpleNamespace(state=SimpleNamespace(engine=engine, gateway=provider, settings=settings))
                gateway = BudgetedGateway(app)
                articles = [Article(**a) for a in json.loads((ROOT / 'knowledge.json').read_text())]
                store = VectorStore(engine)
                index, _ = store.build(articles, gateway, lambda _: None)
                state = AppState(index_id=index)
            for case in cases:
                ticket = Ticket(subject=case['subject'], body=case['body'], original_subject=case['subject'], original_body=case['body'])
                try:
                    result = run_rag(ticket, categories, state, gateway, store, settings) if live else run_rules(ticket, categories)
                except Exception as error:
                    from backend.app.jobs import readable_error
                    result = {'outcome': 'failed', 'latency_ms': 0, 'error': readable_error(error)}
                suggested = result.get('suggestions') or {}
                expected = case['category']
                row = {'id': case['id'], 'expected_category': expected, 'expected_priority': case['priority'],
                       'predicted_category': labels.get(suggested.get('category_id')), 'predicted_priority': suggested.get('priority'),
                       'outcome': result['outcome'], 'latency_ms': result['latency_ms'],
                       'category_correct': labels.get(suggested.get('category_id')) == expected,
                       'priority_correct': suggested.get('priority') == case['priority'],
                       'review_correct': expected is not None or result['outcome'] == 'needs_review'}
                if live:
                    row['retrieval_hit_at_4'] = expected is None or any(s['article_id'] == 'eval-' + expected for s in result.get('retrieved', []))
                    row['quotes_exact'] = bool(result.get('citations')) and all(c['quote'] in c['text'] for c in result['citations'])
                    row['error'] = result.get('error')
                rows.append(row)
        finally:
            if provider:
                provider.close()
            engine.dispose()
    return {'mode': 'live_free_rag' if live else 'offline_rules',
            'limitations': 'Hand-authored fixture set, not independent production data. Rules results do not measure LLM or semantic retrieval quality. Live mode is a small smoke benchmark and varies with provider availability.',
            'metrics': summarize(rows), 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Use configured :free models; at most three cases and seven provider requests.')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    limit = min(args.limit or 3, 3) if args.live else args.limit
    report = benchmark(args.live, limit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report['metrics'], indent=2))


if __name__ == '__main__':
    main()
