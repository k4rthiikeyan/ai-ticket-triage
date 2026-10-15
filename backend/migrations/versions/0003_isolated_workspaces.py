"""Preserve owner data; isolate new demo sessions and persist usage counters."""
from alembic import op
import sqlalchemy as sa
from sqlmodel.sql.sqltypes import UTCDateTime

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('workspace', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('created_at', UTCDateTime(), nullable=False),
                    sa.Column('expires_at', UTCDateTime(), nullable=True), sqlite_autoincrement=True)
    op.create_index('ix_workspace_expires_at', 'workspace', ['expires_at'])
    op.execute(sa.text('INSERT INTO workspace (id, created_at) VALUES (1, CURRENT_TIMESTAMP)'))
    # Existing visitors used the shared owner space. Require a fresh, isolated login.
    op.execute(sa.text("DELETE FROM loginsession WHERE admin_id IN (SELECT id FROM admin WHERE username = 'demo')"))
    for table in ['loginsession', 'ticket', 'article', 'job', 'auditevent']:
        op.add_column(table, sa.Column('workspace_id', sa.Integer(), nullable=False, server_default='1'))
        if table != 'loginsession':
            op.create_index(f'ix_{table}_workspace_id', table, ['workspace_id'])
    op.create_table('usagebucket', sa.Column('id', sa.String(), primary_key=True),
                    sa.Column('count', sa.Integer(), nullable=False),
                    sa.Column('expires_at', UTCDateTime(), nullable=False))
    op.create_index('ix_usagebucket_expires_at', 'usagebucket', ['expires_at'])
    if op.get_context().dialect.name == 'postgresql':
        op.execute(sa.text("SELECT setval(pg_get_serial_sequence('workspace', 'id'), 1)"))


def downgrade():
    op.drop_table('usagebucket')
    for table in ['loginsession', 'ticket', 'article', 'job', 'auditevent']:
        if table != 'loginsession':
            op.drop_index(f'ix_{table}_workspace_id', table_name=table)
        op.drop_column(table, 'workspace_id')
    op.drop_table('workspace')
