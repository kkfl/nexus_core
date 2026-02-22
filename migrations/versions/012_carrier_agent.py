"""carrier_agent

Revision ID: 012_carrier_agent
Revises: 011_storage_task_routes
Create Date: 2026-02-21 04:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '012_carrier_agent'
down_revision = '011_storage_task_routes'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create carrier_targets
    op.create_table(
        'carrier_targets',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), server_default='mock', nullable=False),
        sa.Column('base_url', sa.String(), nullable=True),
        sa.Column('api_key_secret_id', sa.String(), sa.ForeignKey('secrets.id'), nullable=True),
        sa.Column('api_secret_secret_id', sa.String(), sa.ForeignKey('secrets.id'), nullable=True),
        sa.Column('tags', JSONB(), server_default='[]', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='True', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_carrier_targets_id', 'carrier_targets', ['id'])
    op.create_index('ix_carrier_targets_name', 'carrier_targets', ['name'], unique=True)

    # 2. Create carrier_snapshots
    op.create_table(
        'carrier_snapshots',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('carrier_target_id', sa.String(), sa.ForeignKey('carrier_targets.id'), nullable=False),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('summary', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_carrier_snapshots_id', 'carrier_snapshots', ['id'])
    op.create_index('ix_carrier_snapshots_carrier_target_id', 'carrier_snapshots', ['carrier_target_id'])

def downgrade() -> None:
    pass
