"""Atomic SQL counters shared by every application instance; no paid cache service."""
import hashlib
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session
from ..models import UsageBucket, now


def used(session, key, seconds=86400):
    window = int(now().timestamp()) // seconds
    identifier = hashlib.sha256(f'{key}:{seconds}:{window}'.encode()).hexdigest()
    row = session.get(UsageBucket, identifier)
    return row.count if row else 0


def consume(session, key, limit, seconds):
    current = now()
    window = int(current.timestamp()) // seconds
    identifier = hashlib.sha256(f'{key}:{seconds}:{window}'.encode()).hexdigest()
    expires = current + timedelta(seconds=seconds)
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    session.exec(insert(UsageBucket).values(id=identifier, count=0, expires_at=expires).on_conflict_do_nothing(index_elements=['id']))
    changed = session.exec(update(UsageBucket).where(UsageBucket.id == identifier, UsageBucket.count < limit)
                           .values(count=UsageBucket.count + 1).returning(UsageBucket.count)).first()
    if changed is None:
        retry = seconds - int(current.timestamp()) % seconds
        raise HTTPException(429, 'The free demo usage limit has been reached. Wait for the limit to reset; manual decisions and rules remain available.',
                            headers={'Retry-After': str(retry)})


class BudgetedGateway:
    def __init__(self, app, workspace=1, is_demo=False):
        self.app, self.workspace, self.is_demo = app, workspace, is_demo

    def reserve(self):
        settings = self.app.state.settings
        with Session(self.app.state.engine) as session:
            # Every bucket increment commits together, before a provider request.
            consume(session, 'ai:global:day', settings.ai_daily_limit, 86400)
            consume(session, 'ai:global:minute', settings.ai_minute_limit, 60)
            if self.is_demo:
                consume(session, f'ai:workspace:{self.workspace}', settings.demo_ai_daily_limit, 86400)
            session.commit()

    def embed(self, texts):
        self.reserve()
        return self.app.state.gateway.embed(texts)

    def generate(self, messages, schema):
        self.reserve()
        return self.app.state.gateway.generate(messages, schema)
