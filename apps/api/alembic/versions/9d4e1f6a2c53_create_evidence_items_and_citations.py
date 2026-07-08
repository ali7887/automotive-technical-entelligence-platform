"""create evidence items and citations

Revision ID: 9d4e1f6a2c53
Revises: 7c41d2a90b13
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4e1f6a2c53"
down_revision: str | Sequence[str] | None = "7c41d2a90b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVIDENCE_STATUS = sa.Enum(
    "OPEN", "IN_REVIEW", "COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE", name="evidence_status"
)
_EVIDENCE_RISK = sa.Enum("UNRATED", "LOW", "MEDIUM", "HIGH", name="evidence_risk")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("status", _EVIDENCE_STATUS, nullable=False),
        sa.Column("risk", _EVIDENCE_RISK, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_items_workspace_id"), "evidence_items", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_evidence_items_document_id"), "evidence_items", ["document_id"], unique=False
    )

    op.create_table(
        "evidence_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        # provenance snapshot: deliberately no FK to chunks (see models/evidence.py)
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("clause_id", sa.String(length=64), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_citations_evidence_item_id"),
        "evidence_citations",
        ["evidence_item_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_evidence_citations_evidence_item_id"), table_name="evidence_citations")
    op.drop_table("evidence_citations")
    op.drop_index(op.f("ix_evidence_items_document_id"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_workspace_id"), table_name="evidence_items")
    op.drop_table("evidence_items")
    _EVIDENCE_RISK.drop(op.get_bind(), checkfirst=True)
    _EVIDENCE_STATUS.drop(op.get_bind(), checkfirst=True)
