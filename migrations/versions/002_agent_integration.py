"""agent_integration

Revision ID: 002_agent_integration
Revises: 001_initial
Create Date: 2026-02-21 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_agent_integration'
down_revision = '001_initial'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add columns to agents table
    op.add_column('agents', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agents', sa.Column('status', sa.String(), server_default='unknown', nullable=False))
    op.add_column('agents', sa.Column('max_concurrency', sa.Integer(), server_default='2', nullable=False))
    op.add_column('agents', sa.Column('timeout_seconds', sa.Integer(), server_default='30', nullable=False))

    # 2. Create agent_checkins table
    op.create_table(
        'agent_checkins',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_agent_checkins_id', 'agent_checkins', ['id'])

    # 3. Create task_routes table
    op.create_table(
        'task_routes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('required_capabilities', sa.JSON(), nullable=False),
        sa.Column('preferred_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_task_routes_id', 'task_routes', ['id'])
    op.create_index('ix_task_routes_task_type', 'task_routes', ['task_type'], unique=True)

    # 4. Create persona_defaults table
    op.create_table(
        'persona_defaults',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scope_type', sa.String(), nullable=False),
        sa.Column('scope_value', sa.String(), nullable=True),
        sa.Column('persona_version_id', sa.Integer(), sa.ForeignKey('persona_versions.id'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False)
    )
    op.create_index('ix_persona_defaults_id', 'persona_defaults', ['id'])

def downgrade() -> None:
    pass
