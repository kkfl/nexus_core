"""
Service Integrations tables.

Revision ID: 028_service_integrations
Revises: 027_server_agent_tables
Create Date: 2026-03-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "028_service_integrations"
down_revision = "027_server_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- service_integrations ---
    op.create_table(
        "service_integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("service_id", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("api_key_hash", sa.String(128), nullable=False),
        sa.Column("api_key_prefix", sa.String(12), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("permissions", JSONB, nullable=False, server_default='["secrets:read","secrets:list"]'),
        sa.Column("alias_pattern", sa.String(255), nullable=False, server_default="*"),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=True),
        sa.Column("daily_request_limit", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # --- service_usage_log ---
    op.create_table(
        "service_usage_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_id", sa.String(128), nullable=False, index=True),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_service_usage_log_ts_service",
        "service_usage_log",
        ["ts", "service_id"],
    )


def downgrade() -> None:
    op.drop_table("service_usage_log")
    op.drop_table("service_integrations")
