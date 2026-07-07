"""create chunks with fts

Revision ID: 7c41d2a90b13
Revises: 50fff68b954f
Create Date: 2026-07-07 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "7c41d2a90b13"
down_revision: str | Sequence[str] | None = "50fff68b954f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TSVECTOR_SQL = (
    "to_tsvector('english', coalesce(clause_id, '') || ' ' || coalesce(heading, '') || ' ' || text)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("clause_id", sa.String(length=64), nullable=True),
        sa.Column("heading", sa.String(length=512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "text_search",
            TSVECTOR(),
            sa.Computed(_TSVECTOR_SQL, persisted=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_chunks_workspace_id"), "chunks", ["workspace_id"], unique=False)
    op.create_index(
        "ix_chunks_text_search", "chunks", ["text_search"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunks_text_search", table_name="chunks")
    op.drop_index(op.f("ix_chunks_workspace_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
