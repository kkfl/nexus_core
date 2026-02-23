"""015_vault_tables — Create vault_secrets, vault_policies, vault_audit_events, vault_leases."""

import sqlalchemy as sa
from alembic import op

revision = "015_vault_tables"
down_revision = "014_metrics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vault_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alias", sa.String(255), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("env", sa.String(32), nullable=False, index=True),
        sa.Column("description", sa.Text),
        sa.Column("scope_tags", sa.JSON, server_default="[]"),
        sa.Column("encrypted_dek", sa.LargeBinary, nullable=False),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("rotation_interval_days", sa.Integer),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True)),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_service_id", sa.String(128), nullable=False, server_default="system"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("alias", "tenant_id", "env", name="uq_vault_secrets_alias_tenant_env"),
    )
    op.create_index("ix_vault_secrets_tenant_env", "vault_secrets", ["tenant_id", "env"])

    op.create_table(
        "vault_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("alias_pattern", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(128)),
        sa.Column("env", sa.String(32)),
        sa.Column("actions", sa.JSON, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "vault_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, index=True),
        sa.Column("service_id", sa.String(128), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("env", sa.String(32), nullable=False),
        sa.Column("secret_alias", sa.String(255), nullable=False, index=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_vault_audit_ts_service", "vault_audit_events", ["ts", "service_id"])

    op.create_table(
        "vault_leases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("secret_id", sa.String(36), nullable=False, index=True),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("vault_leases")
    op.drop_index("ix_vault_audit_ts_service", table_name="vault_audit_events")
    op.drop_table("vault_audit_events")
    op.drop_table("vault_policies")
    op.drop_index("ix_vault_secrets_tenant_env", table_name="vault_secrets")
    op.drop_table("vault_secrets")
