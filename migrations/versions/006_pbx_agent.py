"""pbx_agent

Revision ID: 006_pbx_agent
Revises: 005_sor_tables
Create Date: 2026-02-21 03:20:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "006_pbx_agent"
down_revision = "005_sor_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create pbx_targets
    op.create_table(
        "pbx_targets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("ami_host", sa.String(), nullable=False),
        sa.Column("ami_port", sa.Integer(), server_default="5038", nullable=False),
        sa.Column("ami_username", sa.String(), nullable=False),
        sa.Column("ami_secret_secret_id", sa.String(), sa.ForeignKey("secrets.id"), nullable=False),
        sa.Column("ami_use_tls", sa.Boolean(), server_default="False", nullable=False),
        sa.Column("tags", JSONB(), server_default="[]", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="True", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pbx_targets_id", "pbx_targets", ["id"])
    op.create_index("ix_pbx_targets_name", "pbx_targets", ["name"], unique=True)

    # 2. Create pbx_snapshots
    op.create_table(
        "pbx_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("pbx_target_id", sa.String(), sa.ForeignKey("pbx_targets.id"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pbx_snapshots_id", "pbx_snapshots", ["id"])
    op.create_index("ix_pbx_snapshots_pbx_target_id", "pbx_snapshots", ["pbx_target_id"])


def downgrade() -> None:
    pass
