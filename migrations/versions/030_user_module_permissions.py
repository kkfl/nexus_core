"""Add module_permissions JSON column to users table.

Revision ID: 030_user_module_permissions
Revises: 029_service_permission_rules
"""

import sqlalchemy as sa
from alembic import op

revision = "030_user_module_permissions"
down_revision = "029_service_permission_rules"
branch_labels = None
depends_on = None

# Default permissions per existing role
_ADMIN_DEFAULTS = {
    "dashboard": "manage",
    "orchestration": "manage",
    "personas": "manage",
    "knowledge_base": "manage",
    "entities": "manage",
    "secrets": "manage",
    "audit": "read",
    "pbx": "manage",
    "monitoring": "manage",
    "storage": "manage",
    "carrier": "manage",
    "email": "manage",
    "dns": "manage",
    "servers": "manage",
    "integrations": "manage",
    "users": "manage",
    "api_keys": "manage",
    "ip_allowlist": "manage",
    "backup": "manage",
}

_OPERATOR_DEFAULTS = {
    "dashboard": "read",
    "orchestration": "manage",
    "personas": "manage",
    "knowledge_base": "manage",
    "entities": "read",
    "secrets": "read",
    "audit": "read",
    "pbx": "manage",
    "monitoring": "manage",
    "storage": "manage",
    "carrier": "manage",
    "email": "manage",
    "dns": "manage",
    "servers": "manage",
    "integrations": "read",
    "users": "none",
    "api_keys": "none",
    "ip_allowlist": "none",
    "backup": "none",
}

_READER_DEFAULTS = {
    "dashboard": "read",
    "orchestration": "read",
    "personas": "read",
    "knowledge_base": "read",
    "entities": "read",
    "secrets": "none",
    "audit": "read",
    "pbx": "read",
    "monitoring": "read",
    "storage": "read",
    "carrier": "read",
    "email": "read",
    "dns": "read",
    "servers": "read",
    "integrations": "none",
    "users": "none",
    "api_keys": "none",
    "ip_allowlist": "none",
    "backup": "none",
}

_ROLE_MAP = {
    "admin": _ADMIN_DEFAULTS,
    "operator": _OPERATOR_DEFAULTS,
    "reader": _READER_DEFAULTS,
}


def upgrade() -> None:
    op.add_column("users", sa.Column("module_permissions", sa.JSON(), nullable=True))

    # Backfill existing users based on their role
    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id, role FROM users")).fetchall()
    for uid, role in users:
        perms = _ROLE_MAP.get(role, _READER_DEFAULTS)
        import json

        conn.execute(
            sa.text("UPDATE users SET module_permissions = :perms WHERE id = :uid"),
            {"perms": json.dumps(perms), "uid": uid},
        )


def downgrade() -> None:
    op.drop_column("users", "module_permissions")
