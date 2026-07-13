"""add chunk structural lineage (parent clause + section path)

Revision ID: d8b2f4a61c39
Revises: c5e8a1f92b47
Create Date: 2026-07-13 14:00:00.000000

Columns are nullable and deliberately NOT part of the chunk identity: existing
rows are backfilled in place by reprocessing (`python -m atip_api.cli
backfill-chunks`), which preserves chunk ids and embeddings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8b2f4a61c39"
down_revision: str | Sequence[str] | None = "c5e8a1f92b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("parent_clause_id", sa.String(length=64), nullable=True))
    op.add_column("chunks", sa.Column("section_path", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "section_path")
    op.drop_column("chunks", "parent_clause_id")
