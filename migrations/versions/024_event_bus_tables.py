"""024 – Event bus tables.

Revision ID: 024_event_bus_tables
Revises: 023_storage_agent_tables
Create Date: 2026-02-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "024_event_bus_tables"
down_revision = "023_storage_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bus_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False, index=True),
        sa.Column("event_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.String(64), nullable=False),
        sa.Column("produced_by", sa.String(128), nullable=False, index=True),
        sa.Column("correlation_id", sa.String(64), index=True),
        sa.Column("causation_id", sa.String(64)),
        sa.Column("actor_type", sa.String(32)),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("tenant_id", sa.String(128), index=True),
        sa.Column("severity", sa.String(16), server_default="info"),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("payload_schema_version", sa.Integer, server_default="1"),
        sa.Column("idempotency_key", sa.String(255), index=True),
        sa.Column("stream_id", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
    )

    # Composite index for common query: time-range + type
    op.create_index(
        "ix_bus_events_type_created",
        "bus_events",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bus_events_type_created", table_name="bus_events")
    op.drop_table("bus_events")
