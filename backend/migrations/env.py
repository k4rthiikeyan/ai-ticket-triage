from alembic import context
from sqlmodel import SQLModel
from backend.app import models

connection = context.config.attributes['connection']
context.configure(connection=connection, target_metadata=SQLModel.metadata)
with context.begin_transaction():
    context.run_migrations()
