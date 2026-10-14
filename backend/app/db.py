from pathlib import Path
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlmodel import create_engine
from .config import Settings


def make_engine(settings: Settings):
    url = settings.database_url
    if url.startswith(('postgres://', 'postgresql://')):
        url = 'postgresql+psycopg://' + url.split('://', 1)[1]
    if os.environ.get('VERCEL') and not url.startswith('postgresql+psycopg://'):
        raise ValueError('Vercel requires a hosted PostgreSQL DATABASE_URL (or POSTGRES_URL). SQLite is only for local development.')
    if url.startswith('sqlite:///'):
        path = url.removeprefix('sqlite:///')
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={'check_same_thread': False})

        @event.listens_for(engine, 'connect')
        def configure_sqlite(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=5000')
            connection.execute('PRAGMA journal_mode=WAL')
    else:
        engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                               connect_args={'connect_timeout': 10, 'prepare_threshold': None})
    return engine


def migrate(engine):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    with engine.begin() as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(871101)'))
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
