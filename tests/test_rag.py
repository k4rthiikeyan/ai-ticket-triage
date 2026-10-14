import json
import pytest
from backend.app.rag import split_text, validate_generation, VectorStore, run_rag
from backend.app.models import Article, Category, Ticket, AppState
from backend.app.config import Settings
from .conftest import FakeGateway, FakeStore
from backend.app.db import make_engine, migrate


def test_chunk_caps_overlap_and_long_paragraphs():
    text = 'A' * 1800 + '\n\n' + 'B' * 1900
    chunks = split_text(text)
    assert len(chunks) > 2 and all(0 < len(c) <= 1200 for c in chunks)
    assert chunks[0][-200:] == chunks[1][:200]
    assert split_text('') == []
    assert split_text('Short paragraph.\n\nAnother one.') == ['Short paragraph.\n\nAnother one.']


def valid_output():
    return {'abstain': False, 'category_id': 1, 'priority': 'normal', 'category_rationale': 'Billing context.', 'priority_rationale': 'Routine request.',
            'category_evidence': [{'chunk_id': 'a', 'quote': 'Billing requests'}], 'priority_evidence': [{'chunk_id': 'a', 'quote': 'normal priority'}]}


@pytest.mark.parametrize('change', [
    {'category_id': 999}, {'priority': 'extreme'}, {'category_evidence': []},
    {'category_evidence': [{'chunk_id': 'invented', 'quote': 'Billing requests'}]},
    {'priority_evidence': [{'chunk_id': 'a', 'quote': 'this quote does not exist'}]},
])
def test_invalid_labels_and_citations_rejected(change):
    category = Category(id=1, slug='billing', name='Billing', queue_id=1)
    source = {'chunk_id': 'a', 'text': 'Billing requests have normal priority.', 'similarity': .75}
    with pytest.raises(ValueError):
        validate_generation(json.dumps({**valid_output(), **change}), [category], [source], [source])


def test_abstention_and_clipped_scores():
    category = Category(id=1, slug='billing', name='Billing', queue_id=1)
    source = {'chunk_id': 'a', 'text': 'Billing requests have normal priority.', 'similarity': 1.001}
    output = validate_generation(json.dumps(valid_output()), [category], [source], [source])
    assert output['scores']['category'] == 1
    assert validate_generation(json.dumps({**valid_output(), 'abstain': True}), [category], [], [])['outcome'] == 'needs_review'


def test_sql_cosine_persistence_and_archived_omission(tmp_path):
    class Embeddings:
        def embed(self, texts):
            return [[1., 0., 0.] if 'Billing' in t else [0., 1., 0.] if 'Technical' in t else [0., 0., 1.] for t in texts]
    articles = [Article(id='b', title='Billing', body='Billing requests have normal priority.'),
                Article(id='t', title='Technical', body='Technical outages are investigated.'),
                Article(id='p', title='Policy', body='Routine requests have normal priority.', is_policy=True)]
    settings = Settings(database_url=f'sqlite:///{(tmp_path / "vectors.db").as_posix()}', _env_file=None)
    engine = make_engine(settings)
    migrate(engine)
    store = VectorStore(engine)
    identifier, count = store.build(articles, Embeddings(), lambda _: None)
    assert count == 3
    reopened = VectorStore(make_engine(settings))
    retrieved, policies = reopened.retrieve(identifier, [1., 0., 0.])
    assert retrieved[0]['article_id'] == 'b' and retrieved[0]['similarity'] == pytest.approx(1)
    assert policies[0]['article_id'] == 'p'
    next_id, _ = store.build([articles[1], articles[2]], Embeddings(), lambda _: None)
    assert all(s['article_id'] != 'b' for s in store.retrieve(next_id, [1., 0., 0.])[0])
    assert store.retrieve(identifier, [1., 0., 0.])[0][0]['article_id'] == 'b'


def test_index_failure_does_not_persist_partial_chunks(tmp_path):
    from sqlmodel import Session, select
    from backend.app.models import KnowledgeChunk
    engine = make_engine(Settings(database_url=f'sqlite:///{(tmp_path / "failed.db").as_posix()}', _env_file=None))
    migrate(engine)
    article = Article(id='own', title='Own article', body='Own knowledge. ' * 3000)
    gateway = FakeGateway()
    gateway.failure = ValueError('Provider failed')
    with pytest.raises(ValueError):
        VectorStore(engine).build([article], gateway, lambda _: None)
    with Session(engine) as session:
        assert session.exec(select(KnowledgeChunk)).all() == []
    with pytest.raises(ValueError, match='up to 1'):
        VectorStore(engine, max_chunks=1).build([article], FakeGateway(), lambda _: None)


def test_long_requests_use_bounded_embedding_chunks(monkeypatch):
    gateway = FakeGateway()
    embedded = []
    original = gateway.embed

    def capture(texts):
        embedded.extend(texts)
        return original(texts)

    monkeypatch.setattr(gateway, 'embed', capture)
    body = 'A duplicate billing charge needs review. ' * 150
    ticket = Ticket(subject='Billing review', body=body, original_subject='Billing review', original_body=body)
    category = Category(id=1, slug='billing', name='Billing', queue_id=1)
    result = run_rag(ticket, [category], AppState(index_id='mock'), gateway, FakeStore(), Settings(_env_file=None))
    assert result['outcome'] == 'suggested'
    assert len(embedded) > 1 and all(len(text) < 1300 for text in embedded)
    assert ticket.body == body
