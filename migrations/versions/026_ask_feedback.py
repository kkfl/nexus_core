"""026 – Ask Feedback table.

Revision ID: 026_ask_feedback
Revises: 025_rag_hardening
Create Date: 2026-03-01
"""

import sqlalchemy as sa
from alembic import op

revision = "026_ask_feedback"
down_revision = "025_rag_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ask_feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("correlation_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("ask_feedback")
