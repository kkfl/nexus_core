"""016_dns_agent_tables — Create dns_zones, dns_records, dns_change_jobs, dns_audit_events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "016_dns_agent_tables"
down_revision = "015_vault_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dns_zones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("zone_name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_zone_id", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dns_zones_tenant", "dns_zones", ["tenant_id"])
    op.create_index("ix_dns_zones_env", "dns_zones", ["env"])
    op.create_index(
        "uq_dns_zones_tenant_env_zone", "dns_zones", ["tenant_id", "env", "zone_name"], unique=True
    )

    op.create_table(
        "dns_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "zone_id",
            sa.String(36),
            sa.ForeignKey("dns_zones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("ttl", sa.Integer, nullable=False, server_default="300"),
        sa.Column("priority", sa.Integer),
        sa.Column("tags", JSONB, server_default="{}"),
        sa.Column("provider_record_id", sa.String(255)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dns_records_zone_id", "dns_records", ["zone_id"])
    op.create_index("ix_dns_records_tenant_env", "dns_records", ["tenant_id", "env"])
    op.create_index(
        "uq_dns_records_zone_type_name",
        "dns_records",
        ["zone_id", "record_type", "name"],
        unique=True,
    )

    op.create_table(
        "dns_change_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("zone_name", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_service_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dns_jobs_tenant", "dns_change_jobs", ["tenant_id"])
    op.create_index("ix_dns_jobs_status", "dns_change_jobs", ["status"])
    op.create_index("ix_dns_jobs_correlation", "dns_change_jobs", ["correlation_id"])
    op.create_index("ix_dns_jobs_created", "dns_change_jobs", ["created_at"])

    op.create_table(
        "dns_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("zone_name", sa.String(255)),
        sa.Column("record_type", sa.String(16)),
        sa.Column("record_name", sa.String(255)),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dns_audit_ts", "dns_audit_events", ["ts"])
    op.create_index("ix_dns_audit_service", "dns_audit_events", ["service_id"])
    op.create_index("ix_dns_audit_tenant", "dns_audit_events", ["tenant_id"])
    op.create_index("ix_dns_audit_correlation", "dns_audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("dns_audit_events")
    op.drop_table("dns_change_jobs")
    op.drop_table("dns_records")
    op.drop_table("dns_zones")
