from io import StringIO
from importlib import import_module
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.app.config import Settings
from backend.app.db import make_engine


def test_postgres_migrations_compile_without_sqlite_specific_sql():
    output = StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        import_module('backend.migrations.versions.0001_initial').upgrade()
        import_module('backend.migrations.versions.0002_knowledge_chunks').upgrade()
        import_module('backend.migrations.versions.0003_isolated_workspaces').upgrade()
    sql = output.getvalue()
    assert 'CREATE TABLE knowledgechunk' in sql
    assert 'CREATE INDEX ix_knowledgechunk_index_id' in sql
    assert 'PRAGMA' not in sql
    assert 'CREATE TABLE workspace' in sql and 'CREATE TABLE usagebucket' in sql


def test_hosted_url_alias_and_psycopg_driver(monkeypatch):
    monkeypatch.setenv('POSTGRES_URL', 'postgres://test:placeholder@localhost/triage?sslmode=require')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    settings = Settings(_env_file=None)
    engine = make_engine(settings)
    try:
        assert engine.dialect.name == 'postgresql' and engine.dialect.driver == 'psycopg'
        assert engine.url.query['sslmode'] == 'require'
    finally:
        engine.dispose()


def test_vercel_rejects_local_database(monkeypatch):
    import pytest
    monkeypatch.setenv('VERCEL', '1')
    with pytest.raises(ValueError, match='hosted PostgreSQL'):
        make_engine(Settings(database_url='sqlite:///:memory:', _env_file=None))
