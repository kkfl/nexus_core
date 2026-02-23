"""security_hardening

Revision ID: 004_security_hardening
Revises: 003_rag_setup
Create Date: 2026-02-21 03:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004_security_hardening"
down_revision = "003_rag_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add refresh_token_hash to users
    op.add_column("users", sa.Column("refresh_token_hash", sa.String(), nullable=True))

    # 2. Create secrets table
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(), primary_key=True),  # UUIDs as strings for simplicity
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_secrets_id", "secrets", ["id"])
    op.create_index("ix_secrets_name", "secrets", ["name"], unique=True)


def downgrade() -> None:
    pass
