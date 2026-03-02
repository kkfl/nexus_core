"""rag_hardening

Revision ID: 025_rag_hardening
Revises: 024_event_bus_tables
Create Date: 2026-02-28 05:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "025_rag_hardening"
down_revision = "024_event_bus_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # kb_documents: add error tracking + versioning
    op.add_column(
        "kb_documents",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "kb_documents",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )

    # kb_chunks: add token count + character offsets for citations
    op.add_column(
        "kb_chunks",
        sa.Column("token_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "kb_chunks",
        sa.Column("start_char", sa.Integer(), nullable=True),
    )
    op.add_column(
        "kb_chunks",
        sa.Column("end_char", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kb_chunks", "end_char")
    op.drop_column("kb_chunks", "start_char")
    op.drop_column("kb_chunks", "token_count")
    op.drop_column("kb_documents", "version")
    op.drop_column("kb_documents", "error_message")
