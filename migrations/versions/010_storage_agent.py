"""storage_agent

Revision ID: 010_storage_agent
Revises: 009_monitoring_task_routes
Create Date: 2026-02-21 04:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '010_storage_agent'
down_revision = '009_monitoring_task_routes'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create storage_targets
    op.create_table(
        'storage_targets',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), server_default='s3', nullable=False),
        sa.Column('endpoint_url', sa.String(), nullable=False),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('bucket', sa.String(), nullable=False),
        sa.Column('access_key_id_secret_id', sa.String(), sa.ForeignKey('secrets.id'), nullable=False),
        sa.Column('secret_access_key_secret_id', sa.String(), sa.ForeignKey('secrets.id'), nullable=False),
        sa.Column('base_prefix', sa.String(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='True', nullable=False),
        sa.Column('tags', JSONB(), server_default='[]', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_storage_targets_id', 'storage_targets', ['id'])
    op.create_index('ix_storage_targets_name', 'storage_targets', ['name'], unique=True)

    # 2. Create storage_jobs
    op.create_table(
        'storage_jobs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('storage_target_id', sa.String(), sa.ForeignKey('storage_targets.id'), nullable=False),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('summary', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_storage_jobs_id', 'storage_jobs', ['id'])
    op.create_index('ix_storage_jobs_storage_target_id', 'storage_jobs', ['storage_target_id'])

def downgrade() -> None:
    pass
