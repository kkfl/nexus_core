"""monitoring_agent

Revision ID: 008_monitoring_agent
Revises: 007_pbx_task_routes
Create Date: 2026-02-21 03:50:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "008_monitoring_agent"
down_revision = "007_pbx_task_routes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create monitoring_sources
    op.create_table(
        "monitoring_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), server_default="nagios", nullable=False),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("auth_secret_id", sa.String(), sa.ForeignKey("secrets.id"), nullable=True),
        sa.Column("tags", JSONB(), server_default="[]", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="True", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_monitoring_sources_id", "monitoring_sources", ["id"])
    op.create_index("ix_monitoring_sources_name", "monitoring_sources", ["name"], unique=True)

    # 2. Create monitoring_ingests
    op.create_table(
        "monitoring_ingests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "monitoring_source_id",
            sa.String(),
            sa.ForeignKey("monitoring_sources.id"),
            nullable=False,
        ),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_monitoring_ingests_id", "monitoring_ingests", ["id"])
    op.create_index(
        "ix_monitoring_ingests_monitoring_source_id", "monitoring_ingests", ["monitoring_source_id"]
    )


def downgrade() -> None:
    pass
