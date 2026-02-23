"""storage agent tables

Revision ID: 023_storage_agent_tables
Revises: 022_monitoring_agent_tables
Create Date: 2026-02-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '023_storage_agent_tables'
down_revision = '022_monitoring_agent_tables'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 0. Drop old prototype tables
    op.drop_table('storage_jobs')
    op.drop_table('storage_targets')
    # 1. storage_targets
    op.create_table(
        'storage_targets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('env', sa.String(), nullable=False, server_default='prod'),
        sa.Column('storage_target_id', sa.String(), nullable=False),
        sa.Column('endpoint_url', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('default_bucket', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('credential_aliases', JSONB, server_default='{}', nullable=False),
        sa.Column('flags', JSONB, server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'env', 'storage_target_id', name='uq_storage_targets_tenant_env_target')
    )

    # 2. storage_buckets
    op.create_table(
        'storage_buckets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('env', sa.String(), nullable=False, server_default='prod'),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('bucket_name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['target_id'], ['storage_targets.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('target_id', 'bucket_name', name='uq_storage_buckets_target_bucket')
    )

    # 3. storage_objects
    op.create_table(
        'storage_objects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('env', sa.String(), nullable=False, server_default='prod'),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('bucket_id', sa.String(), nullable=False),
        sa.Column('object_key', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.Column('tags', JSONB, server_default='{}', nullable=False),
        sa.Column('entity_type', sa.String(), nullable=True),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['target_id'], ['storage_targets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bucket_id'], ['storage_buckets.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('target_id', 'bucket_id', 'object_key', name='uq_storage_objects_target_bucket_key')
    )

    # 4. storage_jobs
    op.create_table(
        'storage_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('env', sa.String(), nullable=False, server_default='prod'),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('payload', JSONB, server_default='{}', nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('correlation_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 5. storage_job_results
    op.create_table(
        'storage_job_results',
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('output_summary', JSONB, server_default='{}', nullable=False),
        sa.Column('completed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('job_id'),
        sa.ForeignKeyConstraint(['job_id'], ['storage_jobs.id'], ondelete='CASCADE')
    )

    # 6. storage_audit_events
    op.create_table(
        'storage_audit_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('correlation_id', sa.String(), nullable=False),
        sa.Column('service_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=True),
        sa.Column('env', sa.String(), nullable=False, server_default='prod'),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=True),
        sa.Column('result', sa.String(), nullable=False),
        sa.Column('detail', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['target_id'], ['storage_targets.id'], ondelete='SET NULL')
    )

def downgrade() -> None:
    op.drop_table('storage_audit_events')
    op.drop_table('storage_job_results')
    op.drop_table('storage_jobs')
    op.drop_table('storage_objects')
    op.drop_table('storage_buckets')
    op.drop_table('storage_targets')
