"""sor_tables

Revision ID: 005_sor_tables
Revises: 004_security_hardening
Create Date: 2026-02-21 03:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "005_sor_tables"
down_revision = "004_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create entities
    op.create_table(
        "entities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("external_ref", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("data", JSONB(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_entities_id", "entities", ["id"])
    op.create_index("ix_entities_kind", "entities", ["kind"])
    op.create_index("ix_entities_external_ref", "entities", ["external_ref"])
    op.create_index("ix_entities_kind_external_ref", "entities", ["kind", "external_ref"])
    op.execute("CREATE INDEX ix_entities_data ON entities USING GIN (data)")

    # 2. Create entity_events
    op.create_table(
        "entity_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("before", JSONB(), nullable=True),
        sa.Column("after", JSONB(), nullable=True),
        sa.Column("diff", JSONB(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_entity_events_id", "entity_events", ["id"])
    op.create_index("ix_entity_events_entity_id", "entity_events", ["entity_id"])
    op.create_index("ix_entity_events_idempotency_key", "entity_events", ["idempotency_key"])

    # Append-only trigger for entity_events
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_update_delete()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'Updates and Deletes are not allowed on this append-only table.';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER entity_events_append_only
    BEFORE UPDATE OR DELETE ON entity_events
    FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();
    """)

    # 3. Create idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("response", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_idempotency_keys_id", "idempotency_keys", ["id"])
    op.create_index("ix_idempotency_keys_key", "idempotency_keys", ["key"], unique=True)

    # 4. Create task_links
    op.create_table(
        "task_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("entity_id", sa.String(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("rel", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_task_links_id", "task_links", ["id"])
    op.create_index("ix_task_links_task_id", "task_links", ["task_id"])
    op.create_index("ix_task_links_entity_id", "task_links", ["entity_id"])


def downgrade() -> None:
    pass
