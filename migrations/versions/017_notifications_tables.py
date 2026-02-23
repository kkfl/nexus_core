"""017_notifications_tables — notification_jobs, deliveries, templates, routing_rules, audit_events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "017_notifications_tables"
down_revision = "016_dns_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("template_id", sa.String(128)),
        sa.Column("subject", sa.Text),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("body_stored", sa.Text),
        sa.Column("sensitivity", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("channels", ARRAY(sa.String), nullable=False),
        sa.Column("routing_rule_id", sa.String(36)),
        sa.Column("context", JSONB),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("idempotency_key", sa.String(256), nullable=False, unique=True),
        sa.Column("idempotency_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("created_by_service_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notif_jobs_tenant", "notification_jobs", ["tenant_id"])
    op.create_index("ix_notif_jobs_status", "notification_jobs", ["status"])
    op.create_index("ix_notif_jobs_idem", "notification_jobs", ["idempotency_key"], unique=True)

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("notification_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("destination_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("provider_msg_id", sa.String(256)),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_detail_redacted", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notif_deliveries_job", "notification_deliveries", ["job_id"])

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("subject_template", sa.Text),
        sa.Column("body_template", sa.Text, nullable=False),
        sa.Column("storage_policy", sa.String(16), nullable=False, server_default="store"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "notification_routing_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("channels", ARRAY(sa.String), nullable=False),
        sa.Column("config", JSONB),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "env", "severity", name="uq_notif_routing"),
    )
    op.create_index("ix_notif_routing_tenant", "notification_routing_rules", ["tenant_id"])

    op.create_table(
        "notification_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("delivery_id", sa.String(36)),
        sa.Column("channel", sa.String(32)),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notif_audit_tenant", "notification_audit_events", ["tenant_id"])
    op.create_index("ix_notif_audit_ts", "notification_audit_events", ["created_at"])
    op.create_index("ix_notif_audit_corr", "notification_audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("notification_audit_events")
    op.drop_table("notification_routing_rules")
    op.drop_table("notification_templates")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_jobs")
