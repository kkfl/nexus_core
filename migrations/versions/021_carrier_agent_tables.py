"""carrier_agent_tables

Revision ID: 021_carrier_agent_tables
Revises: 020_pbx_agent_tables
Create Date: 2026-02-22 22:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '021_carrier_agent_tables'
down_revision = '020_pbx_agent_tables'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('carrier_targets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('env', sa.String(length=20), nullable=False, server_default='prod'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('credential_aliases', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('default_region', sa.String(length=50), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'env', 'name', name='uq_carrier_target_name_tenant')
    )
    op.create_index(op.f('ix_carrier_targets_tenant_id'), 'carrier_targets', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_carrier_targets_env'), 'carrier_targets', ['env'], unique=False)

    op.create_table('carrier_did_inventory',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('env', sa.String(length=20), nullable=False, server_default='prod'),
        sa.Column('carrier_target_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.String(length=50), nullable=False),
        sa.Column('provider_sid', sa.String(length=100), nullable=True),
        sa.Column('capabilities', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('purchased_at', sa.DateTime(), nullable=False),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carrier_target_id'], ['carrier_targets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('carrier_target_id', 'number', name='uq_carrier_did_number_target')
    )
    op.create_index(op.f('ix_carrier_did_inventory_tenant_id'), 'carrier_did_inventory', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_carrier_did_inventory_number'), 'carrier_did_inventory', ['number'], unique=False)

    op.create_table('carrier_trunk_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('env', sa.String(length=20), nullable=False, server_default='prod'),
        sa.Column('carrier_target_id', sa.String(length=36), nullable=False),
        sa.Column('trunk_id', sa.String(length=100), nullable=False),
        sa.Column('friendly_name', sa.String(length=255), nullable=False),
        sa.Column('termination_sip_domain', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['carrier_target_id'], ['carrier_targets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('carrier_target_id', 'trunk_id', name='uq_carrier_trunk_id_target')
    )
    op.create_index(op.f('ix_carrier_trunk_records_tenant_id'), 'carrier_trunk_records', ['tenant_id'], unique=False)

    op.create_table('carrier_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('env', sa.String(length=20), nullable=False, server_default='prod'),
        sa.Column('carrier_target_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('payload_redacted', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('error_redacted', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['carrier_target_id'], ['carrier_targets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_carrier_jobs_tenant_id'), 'carrier_jobs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_carrier_jobs_status'), 'carrier_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_carrier_jobs_next_retry_at'), 'carrier_jobs', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_carrier_jobs_correlation_id'), 'carrier_jobs', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_carrier_jobs_idempotency_key'), 'carrier_jobs', ['idempotency_key'], unique=False)

    op.create_table('carrier_job_results',
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('output_summary_safe', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['carrier_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id')
    )

    op.create_table('carrier_audit_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('env', sa.String(length=20), nullable=False, server_default='prod'),
        sa.Column('correlation_id', sa.String(length=100), nullable=True),
        sa.Column('service_id', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('result', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('target_id', sa.String(length=36), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_carrier_audit_events_tenant_id'), 'carrier_audit_events', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_carrier_audit_events_env'), 'carrier_audit_events', ['env'], unique=False)
    op.create_index(op.f('ix_carrier_audit_events_correlation_id'), 'carrier_audit_events', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_carrier_audit_events_timestamp'), 'carrier_audit_events', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_table('carrier_audit_events')
    op.drop_table('carrier_job_results')
    op.drop_table('carrier_jobs')
    op.drop_table('carrier_trunk_records')
    op.drop_table('carrier_did_inventory')
    op.drop_table('carrier_targets')
