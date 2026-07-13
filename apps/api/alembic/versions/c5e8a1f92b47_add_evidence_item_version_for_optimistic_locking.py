"""add evidence item version for optimistic locking

Revision ID: c5e8a1f92b47
Revises: b7a3c9e51d24
Create Date: 2026-07-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e8a1f92b47"
down_revision: str | Sequence[str] | None = "b7a3c9e51d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "version")
