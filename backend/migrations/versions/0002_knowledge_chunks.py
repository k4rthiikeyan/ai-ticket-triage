"""Store embedding snapshots in the shared SQL database."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('knowledgechunk',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('index_id', sa.String(), nullable=False),
        sa.Column('chunk_id', sa.String(), nullable=False),
        sa.Column('article_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('article_revision', sa.Integer(), nullable=False),
        sa.Column('is_policy', sa.Boolean(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=False))
    op.create_index('ix_knowledgechunk_index_id', 'knowledgechunk', ['index_id'])
    op.create_index('ix_job_status_created_at', 'job', ['status', 'created_at'])


def downgrade():
    op.drop_index('ix_job_status_created_at', table_name='job')
    op.drop_table('knowledgechunk')
