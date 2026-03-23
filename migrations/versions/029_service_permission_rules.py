"""
Service Permission Rules table.

Revision ID: 029_service_permission_rules
Revises: 028_service_integrations
Create Date: 2026-03-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "029_service_permission_rules"
down_revision = "028_service_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_permission_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "service_integration_id",
            sa.String(36),
            sa.ForeignKey("service_integrations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_pattern", sa.String(255), nullable=False, server_default="*"),
        sa.Column("actions", JSONB, nullable=False, server_default='["read"]'),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=True),
        sa.Column("daily_limit", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_perm_rules_svc_resource",
        "service_permission_rules",
        ["service_integration_id", "resource_type"],
    )


def downgrade() -> None:
    op.drop_table("service_permission_rules")
