"""metrics_events

Revision ID: 014_metrics_events
Revises: 013_carrier_task_routes
Create Date: 2026-02-21 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_metrics_events'
down_revision = '013_carrier_task_routes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'metrics_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_metrics_events_name', 'metrics_events', ['name'])
    op.create_index('ix_metrics_events_created_at', 'metrics_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_metrics_events_created_at', table_name='metrics_events')
    op.drop_index('ix_metrics_events_name', table_name='metrics_events')
    op.drop_table('metrics_events')
