"""add review workflow and audit trail

Revision ID: b7a3c9e51d24
Revises: 9d4e1f6a2c53
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7a3c9e51d24"
down_revision: str | Sequence[str] | None = "9d4e1f6a2c53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVIEW_STATUS_VALUES = ("NEW", "IN_REVIEW", "APPROVED", "REJECTED", "NEEDS_REVISION")
_REVIEW_ACTION_VALUES = (
    "START_REVIEW",
    "APPROVE",
    "REJECT",
    "REQUEST_REVISION",
    "COMMENT",
    "SET_RISK",
    "SET_STATUS",
    "EXTRACTION_ARCHIVED",
)
_ACTOR_TYPE_VALUES = ("HUMAN", "SYSTEM")
_EVIDENCE_RISK_VALUES = ("UNRATED", "LOW", "MEDIUM", "HIGH")


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    """Reference an already-created Postgres enum type."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    postgresql.ENUM(*_REVIEW_STATUS_VALUES, name="review_status").create(bind, checkfirst=True)
    postgresql.ENUM(*_REVIEW_ACTION_VALUES, name="review_action").create(bind, checkfirst=True)
    postgresql.ENUM(*_ACTOR_TYPE_VALUES, name="actor_type").create(bind, checkfirst=True)

    op.add_column(
        "evidence_items",
        sa.Column(
            "review_status",
            _enum("review_status", _REVIEW_STATUS_VALUES),
            nullable=False,
            server_default="NEW",
        ),
    )
    op.add_column(
        "evidence_items", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_evidence_items_review_status"), "evidence_items", ["review_status"], unique=False
    )

    op.create_table(
        "evidence_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        # monotonic tiebreaker: created_at is transaction-fixed, so events
        # written in one request would otherwise have no deterministic order
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("action", _enum("review_action", _REVIEW_ACTION_VALUES), nullable=False),
        sa.Column("previous_status", _enum("review_status", _REVIEW_STATUS_VALUES), nullable=False),
        sa.Column("next_status", _enum("review_status", _REVIEW_STATUS_VALUES), nullable=False),
        sa.Column("previous_risk", _enum("evidence_risk", _EVIDENCE_RISK_VALUES), nullable=False),
        sa.Column("next_risk", _enum("evidence_risk", _EVIDENCE_RISK_VALUES), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_name", sa.String(length=120), nullable=False),
        sa.Column("actor_type", _enum("actor_type", _ACTOR_TYPE_VALUES), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index(
        op.f("ix_evidence_review_events_evidence_item_id"),
        "evidence_review_events",
        ["evidence_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_review_events_item_seq",
        "evidence_review_events",
        ["evidence_item_id", "seq"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_evidence_review_events_item_seq", table_name="evidence_review_events")
    op.drop_index(
        op.f("ix_evidence_review_events_evidence_item_id"), table_name="evidence_review_events"
    )
    op.drop_table("evidence_review_events")
    op.drop_index(op.f("ix_evidence_items_review_status"), table_name="evidence_items")
    op.drop_column("evidence_items", "archived_at")
    op.drop_column("evidence_items", "review_status")
    postgresql.ENUM(name="actor_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="review_action").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="review_status").drop(op.get_bind(), checkfirst=True)
