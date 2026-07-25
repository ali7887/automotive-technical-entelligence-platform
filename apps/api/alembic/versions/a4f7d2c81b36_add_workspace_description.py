"""add workspace description

Revision ID: a4f7d2c81b36
Revises: e9c3a5b72d41
Create Date: 2026-07-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4f7d2c81b36"
down_revision: str | Sequence[str] | None = "e9c3a5b72d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "description")
