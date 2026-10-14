from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

Priority = Literal['low', 'normal', 'high', 'urgent']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class LoginBody(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TicketCreate(StrictModel):
    subject: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=10, max_length=12000)


class TicketUpdate(StrictModel):
    expected_revision: int
    subject: str | None = Field(default=None, min_length=3, max_length=180)
    body: str | None = Field(default=None, min_length=10, max_length=12000)
    status: Literal['open', 'resolved'] | None = None


class NoteBody(StrictModel):
    body: str = Field(min_length=1, max_length=4000)


class DecisionBody(StrictModel):
    expected_revision: int
    category_id: int
    priority: Priority
    queue_id: int
    recommendation_id: str | None = None
    note: str = Field(default='', max_length=2000)


class ArticleBody(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=30, max_length=50000)
    is_policy: bool = False


class KnowledgeSearch(StrictModel):
    query: str = Field(min_length=3, max_length=12000)
    limit: int = Field(default=4, ge=1, le=10)


class ArticleUpdate(StrictModel):
    expected_revision: int
    title: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=30, max_length=50000)
    active: bool = True


class QueueBody(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    active: bool = True


class CategoryBody(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    queue_id: int
    keywords: list[str] = Field(default_factory=list, max_length=30)
    active: bool = True

    @field_validator('keywords')
    @classmethod
    def clean_keywords(cls, value):
        if any(not word.strip() or len(word) > 80 for word in value):
            raise ValueError('Keywords must contain 1–80 characters')
        return sorted(set(word.strip().lower() for word in value))


class Evidence(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=5, max_length=600)


class GeneratedTriage(StrictModel):
    abstain: bool
    category_id: int | None
    priority: Priority | None
    category_rationale: str = Field(max_length=700)
    priority_rationale: str = Field(max_length=700)
    category_evidence: list[Evidence] = Field(max_length=4)
    priority_evidence: list[Evidence] = Field(max_length=4)
