"""Upgrade a populated old schema, including the formerly shared demo session."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlmodel import Session
from backend.app.config import Settings
from backend.app.db import make_engine, migrate
from backend.app.models import LoginSession, Workspace, Article, Ticket


def test_upgrade_preserves_owner_content_and_revokes_shared_demo_session(tmp_path):
    engine = make_engine(Settings(database_url=f'sqlite:///{tmp_path / "old.db"}', _env_file=None))
    root = Path(__file__).resolve().parents[1] / 'backend'
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0002')
        connection.execute(text("INSERT INTO admin (id, username, password_hash) VALUES (1, 'owner', 'unused'), (2, 'demo', 'unused')"))
        connection.execute(text("INSERT INTO loginsession (token_hash, admin_id, csrf_token, expires_at) VALUES ('owner-token', 1, 'x', '2099-01-01'), ('shared-demo-token', 2, 'y', '2099-01-01')"))
        connection.execute(text("INSERT INTO article (id, title, body, revision, is_policy, active, updated_at) VALUES ('kept', 'Owner knowledge', 'Keep this owner knowledge intact.', 1, false, true, CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO ticket (id, subject, body, original_subject, original_body, revision, status, created_at, updated_at) VALUES (1, 'Owner ticket', 'Keep this request', 'Owner ticket', 'Keep this request', 1, 'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    migrate(engine)
    migrate(engine)
    with Session(engine) as session:
        assert session.get(Workspace, 1)
        assert session.get(LoginSession, 'owner-token').workspace_id == 1
        assert session.get(LoginSession, 'shared-demo-token') is None
        assert session.get(Article, 'kept').workspace_id == 1
        assert session.get(Ticket, 1).body == 'Keep this request'
    engine.dispose()
