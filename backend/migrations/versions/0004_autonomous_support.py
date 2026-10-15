"""Customer ownership, resolution lifecycle, and public conversation history."""
from alembic import op
import sqlalchemy as sa
from sqlmodel.sql.sqltypes import UTCDateTime

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    for name, kind, default, nullable in [
        ('customer_id', sa.String(), None, True),
        ('resolution_state', sa.String(), 'unprocessed', False),
        ('outcome_version', sa.Integer(), '0', False),
        ('review_reason', sa.String(), '', False),
        ('review_note', sa.String(), '', False),
        ('answer', sa.String(), '', False),
        ('draft_run_id', sa.String(), None, True),
    ]:
        op.add_column('ticket', sa.Column(name, kind, nullable=nullable, server_default=default))
    op.create_index('ix_ticket_customer_id', 'ticket', ['customer_id'])
    op.create_index('ix_ticket_resolution_state', 'ticket', ['resolution_state'])
    op.create_table('customersession',
        sa.Column('token_hash', sa.String(), primary_key=True),
        sa.Column('customer_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('csrf_token', sa.String(), nullable=False),
        sa.Column('expires_at', UTCDateTime(), nullable=False))
    op.create_index('ix_customersession_customer_id', 'customersession', ['customer_id'], unique=True)
    op.create_index('ix_customersession_workspace_id', 'customersession', ['workspace_id'])
    op.create_index('ix_customersession_expires_at', 'customersession', ['expires_at'])
    op.create_table('ticketmessage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('ticket.id'), nullable=False),
        sa.Column('author', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('citations', sa.JSON(), nullable=False),
        sa.Column('created_at', UTCDateTime(), nullable=False))
    op.create_index('ix_ticketmessage_ticket_id', 'ticketmessage', ['ticket_id'])


def downgrade():
    op.drop_table('ticketmessage')
    op.drop_table('customersession')
    op.drop_index('ix_ticket_customer_id', table_name='ticket')
    op.drop_index('ix_ticket_resolution_state', table_name='ticket')
    for name in ['draft_run_id', 'answer', 'review_note', 'review_reason', 'outcome_version', 'resolution_state', 'customer_id']:
        op.drop_column('ticket', name)
