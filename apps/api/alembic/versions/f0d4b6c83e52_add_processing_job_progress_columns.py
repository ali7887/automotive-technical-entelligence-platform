"""add processing job progress columns (stage, attempts, request_id)

Revision ID: f0d4b6c83e52
Revises: d8b2f4a61c39
Create Date: 2026-07-13 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0d4b6c83e52"
down_revision: str | Sequence[str] | None = "d8b2f4a61c39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("stage", sa.String(length=32), nullable=True))
    op.add_column(
        "processing_jobs",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("processing_jobs", sa.Column("request_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "request_id")
    op.drop_column("processing_jobs", "attempts")
    op.drop_column("processing_jobs", "stage")
