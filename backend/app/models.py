from datetime import datetime, timezone
from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


class Admin(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str


class Workspace(SQLModel, table=True):
    __table_args__ = {'sqlite_autoincrement': True}
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime | None = Field(default=None, index=True)


class LoginSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    admin_id: int = Field(foreign_key='admin.id')
    csrf_token: str
    expires_at: datetime
    workspace_id: int = Field(default=1)


class Queue(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    active: bool = True


class Category(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True)
    name: str = Field(unique=True)
    queue_id: int = Field(foreign_key='queue.id')
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    active: bool = True


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(default=1, index=True)
    seed_key: str | None = Field(default=None, unique=True)
    subject: str
    body: str
    original_subject: str
    original_body: str
    revision: int = 1
    status: str = Field(default='new', index=True)
    category_id: int | None = Field(default=None, foreign_key='category.id', index=True)
    priority: str | None = Field(default=None, index=True)
    queue_id: int | None = Field(default=None, foreign_key='queue.id')
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class TicketRevision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key='ticket.id', index=True)
    revision: int
    subject: str
    body: str
    created_at: datetime = Field(default_factory=now)


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key='ticket.id', index=True)
    body: str
    created_at: datetime = Field(default_factory=now)


class Article(SQLModel, table=True):
    id: str = Field(primary_key=True)
    workspace_id: int = Field(default=1, index=True)
    title: str
    body: str
    revision: int = 1
    is_policy: bool = False
    active: bool = True
    updated_at: datetime = Field(default_factory=now)


class ArticleRevision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    article_id: str = Field(foreign_key='article.id', index=True)
    revision: int
    title: str
    body: str
    active: bool
    created_at: datetime = Field(default_factory=now)


class AppState(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    knowledge_version: int = 1
    taxonomy_version: int = 1
    index_knowledge_version: int = 0
    index_id: str | None = None
    embedding_model: str | None = None


class KnowledgeChunk(SQLModel, table=True):
    id: str = Field(primary_key=True)
    index_id: str = Field(index=True)
    chunk_id: str
    article_id: str
    title: str
    article_revision: int
    is_policy: bool = False
    text: str
    embedding: list[float] = Field(sa_column=Column(JSON, nullable=False))


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    workspace_id: int = Field(default=1, index=True)
    kind: str
    ticket_id: int | None = Field(default=None, foreign_key='ticket.id')
    status: str = 'queued'
    progress: str = 'Waiting to start'
    error: str | None = None
    result: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None


class RecommendationRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    ticket_id: int = Field(foreign_key='ticket.id', index=True)
    ticket_revision: int
    taxonomy_version: int
    index_version: str | None = None
    method: str
    model: str
    outcome: str
    payload: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Decision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key='ticket.id', index=True)
    ticket_revision: int
    recommendation_id: str | None = Field(default=None, foreign_key='recommendationrun.id')
    category_id: int = Field(foreign_key='category.id')
    priority: str
    queue_id: int = Field(foreign_key='queue.id')
    action: str
    note: str = ''
    created_at: datetime = Field(default_factory=now)


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(default=1, index=True)
    ticket_id: int | None = Field(default=None, foreign_key='ticket.id', index=True)
    actor: str = 'admin'
    action: str
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class UsageBucket(SQLModel, table=True):
    id: str = Field(primary_key=True)
    count: int = 0
    expires_at: datetime = Field(index=True)
