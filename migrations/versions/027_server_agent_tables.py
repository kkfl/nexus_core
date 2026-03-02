"""
Server Agent tables.

Revision ID: 027_server_agent_tables
Revises: 026_ask_feedback
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "027_server_agent_tables"
down_revision = "026_ask_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- server_hosts ---
    op.create_table(
        "server_hosts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("env", sa.String(32), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("secret_alias", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_server_hosts_tenant_env_label",
        "server_hosts",
        ["tenant_id", "env", "label"],
        unique=True,
    )

    # --- server_instances ---
    op.create_table(
        "server_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "host_id",
            sa.String(36),
            sa.ForeignKey("server_hosts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_instance_id", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255)),
        sa.Column("os", sa.String(128)),
        sa.Column("plan", sa.String(128)),
        sa.Column("region", sa.String(128)),
        sa.Column("ip_v4", sa.String(45)),
        sa.Column("ip_v6", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("power_status", sa.String(32), server_default="off"),
        sa.Column("vcpu_count", sa.Integer),
        sa.Column("ram_mb", sa.Integer),
        sa.Column("disk_gb", sa.Integer),
        sa.Column("tags", JSONB, server_default="{}"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_server_inst_host_provider_id",
        "server_instances",
        ["host_id", "provider_instance_id"],
        unique=True,
    )
    op.create_index(
        "ix_server_inst_tenant_env",
        "server_instances",
        ["tenant_id", "env"],
    )

    # --- server_snapshots ---
    op.create_table(
        "server_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "instance_id",
            sa.String(36),
            sa.ForeignKey("server_instances.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_snapshot_id", sa.String(255)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("size_gb", sa.Float),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- server_backups ---
    op.create_table(
        "server_backups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "instance_id",
            sa.String(36),
            sa.ForeignKey("server_instances.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_backup_id", sa.String(255)),
        sa.Column("backup_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("size_gb", sa.Float),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- server_change_jobs ---
    op.create_table(
        "server_change_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column(
            "instance_id",
            sa.String(36),
            sa.ForeignKey("server_instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_service_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # --- server_audit_events ---
    op.create_table(
        "server_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(64), nullable=False, index=True),
        sa.Column("service_id", sa.String(128), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("instance_label", sa.String(255)),
        sa.Column("provider", sa.String(64)),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index(
        "ix_server_audit_ts_service",
        "server_audit_events",
        ["ts", "service_id"],
    )


def downgrade() -> None:
    op.drop_table("server_audit_events")
    op.drop_table("server_change_jobs")
    op.drop_table("server_backups")
    op.drop_table("server_snapshots")
    op.drop_table("server_instances")
    op.drop_table("server_hosts")
