import math
from uuid import uuid4
from sqlmodel import Session, select
from ..models import KnowledgeChunk

def split_text(text: str, cap: int = 1200, overlap: int = 200) -> list[str]:
    """Prefer paragraph boundaries; long paragraphs use safe character windows."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + cap, len(text))
        if end < len(text):
            boundary = text.rfind('\n\n', start + cap // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


class VectorStore:
    """Bounded cosine search over SQL embedding snapshots for a small prototype."""
    def __init__(self, engine, max_chunks=256):
        self.engine = engine
        self.max_chunks = max_chunks

    def build(self, articles, gateway, progress):
        if not any(not article.is_policy and article.active for article in articles):
            raise ValueError('Add at least one active support article before rebuilding the index.')
        index_id = 'kb_' + uuid4().hex
        rows = []
        for article in articles:
            if not article.active:
                continue
            for index, text in enumerate(split_text(article.body)):
                chunk_id = f'{article.id}:v{article.revision}:{index}'
                rows.append(KnowledgeChunk(id=f'{index_id}:{chunk_id}', index_id=index_id,
                    chunk_id=chunk_id, article_id=article.id, title=article.title,
                    article_revision=article.revision, is_policy=article.is_policy, text=text, embedding=[]))
        if len(rows) > self.max_chunks:
            raise ValueError(f'This prototype supports up to {self.max_chunks} knowledge chunks. Shorten or archive articles.')
        # Persist only after every embedding succeeds, preserving the active index on failure.
        dimension = None
        with Session(self.engine) as session:
            for start in range(0, len(rows), 16):
                batch = rows[start:start + 16]
                progress(f'Embedding {min(start + 16, len(rows))} of {len(rows)} chunks')
                vectors = gateway.embed([f'{r.title}\n\n{r.text}' for r in batch])
                if len(vectors) != len(batch):
                    raise ValueError('The embedding model omitted article vectors.')
                for row, vector in zip(batch, vectors):
                    dimension = dimension or len(vector)
                    if not dimension or len(vector) != dimension:
                        raise ValueError('The embedding model returned inconsistent dimensions.')
                    row.embedding = vector
                    session.add(row)
            progress('Saving knowledge embeddings')
            session.commit()
        return index_id, len(rows)

    def retrieve(self, index_id, vector, top_k=4):
        with Session(self.engine) as session:
            rows = session.exec(select(KnowledgeChunk).where(KnowledgeChunk.index_id == index_id)).all()
        if not rows:
            raise ValueError('The knowledge index is unavailable. Rebuild it using your own articles.')
        results, policies = [], []
        for row in rows:
            embedding = row.embedding
            if len(embedding) != len(vector):
                raise ValueError('Embedding dimensions changed. Rebuild the knowledge index.')
            denom = math.sqrt(sum(x * x for x in vector) * sum(x * x for x in embedding))
            similarity = sum(a * b for a, b in zip(vector, embedding)) / denom if denom else 0
            source = {'chunk_id': row.chunk_id, 'text': row.text, 'article_id': row.article_id,
                      'title': row.title, 'article_revision': row.article_revision,
                      'similarity': round(max(-1, min(1, similarity)), 4)}
            (policies if row.is_policy else results).append(source)
        results.sort(key=lambda source: (-source['similarity'], source['chunk_id']))
        return results[:top_k], policies


def embed_query(text, gateway):
    vectors = gateway.embed(split_text(text))
    if not vectors or not vectors[0]:
        raise ValueError('The embedding model returned an empty query vector.')
    vector = [sum(row[i] for row in vectors) / len(vectors) for i in range(len(vectors[0]))]
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


