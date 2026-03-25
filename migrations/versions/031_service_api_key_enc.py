"""Add api_key_enc column to service_integrations for break-glass reveal.

Revision ID: 031_service_api_key_enc
Revises: 030_user_module_permissions
"""

import sqlalchemy as sa
from alembic import op

revision = "031_service_api_key_enc"
down_revision = "030_user_module_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_integrations",
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("service_integrations", "api_key_enc")
