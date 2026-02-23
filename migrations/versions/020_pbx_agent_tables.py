"""pbx_agent tables

Revision ID: 020_pbx_agent_tables
Revises: 019_automation_tables
Create Date: 2026-02-22 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "020_pbx_agent_tables"
down_revision = "019_automation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pbx_targets
    op.create_table(
        "pbx_targets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(256), nullable=False),
        sa.Column("ami_port", sa.Integer(), nullable=False, server_default="5038"),
        sa.Column("ami_username", sa.String(128), nullable=False),
        sa.Column("ami_secret_alias", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbx_targets_tenant_env", "pbx_targets", ["tenant_id", "env"])

    # pbx_jobs
    op.create_table(
        "pbx_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(64), nullable=False),
        sa.Column("pbx_target_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("payload_redacted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pbx_target_id"], ["pbx_targets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbx_jobs_status", "pbx_jobs", ["status"])
    op.create_index("ix_pbx_jobs_tenant", "pbx_jobs", ["tenant_id"])

    # pbx_job_results
    op.create_table(
        "pbx_job_results",
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("output_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_redacted", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["pbx_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )

    # pbx_audit_events
    op.create_table(
        "pbx_audit_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("env", sa.String(64), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbx_audit_tenant", "pbx_audit_events", ["tenant_id"])
    op.create_index("ix_pbx_audit_correlation", "pbx_audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("pbx_audit_events")
    op.drop_table("pbx_job_results")
    op.drop_table("pbx_jobs")
    op.drop_table("pbx_targets")
