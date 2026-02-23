"""rag_setup

Revision ID: 003_rag_setup
Revises: 002_agent_integration
Create Date: 2026-02-21 02:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "003_rag_setup"
down_revision = "002_agent_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add fields to task_routes
    op.add_column(
        "task_routes", sa.Column("needs_rag", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("task_routes", sa.Column("rag_namespaces", sa.JSON(), nullable=True))
    op.add_column("task_routes", sa.Column("rag_top_k", sa.Integer(), nullable=True))

    # 2. kb_sources
    op.create_table(
        "kb_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kb_sources_id", "kb_sources", ["id"])
    op.create_index("ix_kb_sources_name", "kb_sources", ["name"], unique=True)

    # 3. kb_documents
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("kb_sources.id"), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("bytes_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("ingest_status", sa.String(), server_default="uploaded", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kb_documents_id", "kb_documents", ["id"])
    op.create_index("ix_kb_documents_namespace", "kb_documents", ["namespace"])

    # 4. kb_chunks
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("kb_documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunks_doc_idx"),
    )
    op.create_index("ix_kb_chunks_id", "kb_chunks", ["id"])

    # 5. kb_embeddings
    op.create_table(
        "kb_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("kb_chunks.id"), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("chunk_id", name="uq_kb_embeddings_chunk_id"),
    )
    op.create_index("ix_kb_embeddings_id", "kb_embeddings", ["id"])
    # Add HNSW index
    op.execute("CREATE INDEX ON kb_embeddings USING hnsw (embedding vector_cosine_ops);")

    # 6. kb_access_logs
    op.create_table(
        "kb_access_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("namespaces", sa.JSON(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kb_access_logs_id", "kb_access_logs", ["id"])


def downgrade() -> None:
    pass
