"""monitoring_agent_tables

Revision ID: 022_monitoring_agent_tables
Revises: 021_carrier_agent_tables
Create Date: 2026-02-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "022_monitoring_agent_tables"
down_revision = "021_carrier_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop old prototype tables (they were added in 008, so safe to drop in V1)
    op.drop_table("monitoring_ingests")
    op.drop_table("monitoring_sources")

    # 2. Add full V1 schema
    # -- monitoring_targets --
    op.create_table(
        "monitoring_targets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("env", sa.String(), server_default="prod", nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="True", nullable=False),
        sa.Column("tags", JSONB(), server_default="[]", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_monitoring_targets_id", "monitoring_targets", ["id"])
    op.create_index("ix_monitoring_targets_tenant_env", "monitoring_targets", ["tenant_id", "env"])
    op.create_index("ix_monitoring_targets_agent_name", "monitoring_targets", ["agent_name"])

    # -- monitoring_state --
    op.create_table(
        "monitoring_state",
        sa.Column(
            "target_id",
            sa.String(),
            sa.ForeignKey("monitoring_targets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("current_state", sa.String(), nullable=False),  # UP, DOWN, DEGRADED
        sa.Column("last_state_change_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_alerted_at", sa.DateTime(), nullable=True),
        sa.Column("alert_cooldown_until", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_monitoring_state_target", "monitoring_state", ["target_id"])

    # -- monitoring_checks --
    op.create_table(
        "monitoring_checks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "target_id",
            sa.String(),
            sa.ForeignKey("monitoring_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("health_status_code", sa.Integer(), nullable=True),
        sa.Column("ready_status_code", sa.Integer(), nullable=True),
        sa.Column("health_ok", sa.Boolean(), nullable=False),
        sa.Column("ready_ok", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_detail_redacted", sa.String(), nullable=True),
        sa.Column("capabilities_hash", sa.String(), nullable=True),
    )
    op.create_index("ix_monitoring_checks_id", "monitoring_checks", ["id"])
    op.create_index("ix_monitoring_checks_target", "monitoring_checks", ["target_id"])
    op.create_index("ix_monitoring_checks_started", "monitoring_checks", ["started_at"])

    # -- monitoring_audit_events --
    op.create_table(
        "monitoring_audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("service_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("env", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column(
            "target_id",
            sa.String(),
            sa.ForeignKey("monitoring_targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_monitoring_audit_events_id", "monitoring_audit_events", ["id"])
    op.create_index("ix_monitoring_audit_events_target", "monitoring_audit_events", ["target_id"])
    op.create_index(
        "ix_monitoring_audit_events_corr", "monitoring_audit_events", ["correlation_id"]
    )


def downgrade() -> None:
    pass
