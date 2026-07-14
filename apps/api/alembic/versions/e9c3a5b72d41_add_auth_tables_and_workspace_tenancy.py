"""add auth tables (organizations, users, workspace_members, sessions) and workspace tenancy

Revision ID: e9c3a5b72d41
Revises: f0d4b6c83e52
Create Date: 2026-07-13 16:00:00.000000

Existing workspaces (created before auth existed) are adopted into a
deterministic "Default Organization" so the upgrade is safe on a live DB;
an org_admin created via `python -m atip_api.cli create-user` in that org
regains access to all of them.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9c3a5b72d41"
down_revision: str | Sequence[str] | None = "f0d4b6c83e52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# uuid5 so re-running against a restored dump yields the same org id
_DEFAULT_ORG_ID = uuid.uuid5(uuid.NAMESPACE_URL, "atip:default-organization")
_DEFAULT_ORG_NAME = "Default Organization"


def upgrade() -> None:
    user_role = sa.Enum("PLATFORM_ADMIN", "ORG_ADMIN", "MEMBER", name="user_role")
    workspace_role = sa.Enum("WORKSPACE_EDITOR", "WORKSPACE_VIEWER", name="workspace_role")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", workspace_role, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # tenancy column: add nullable, adopt orphans, then tighten to NOT NULL
    op.add_column("workspaces", sa.Column("organization_id", sa.Uuid(), nullable=True))
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text("SELECT count(*) FROM workspaces WHERE organization_id IS NULL")
    ).scalar()
    if orphans:
        conn.execute(
            sa.text(
                "INSERT INTO organizations (id, name) VALUES (:id, :name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"id": _DEFAULT_ORG_ID, "name": _DEFAULT_ORG_NAME},
        )
        org_id = conn.execute(
            sa.text("SELECT id FROM organizations WHERE name = :name"),
            {"name": _DEFAULT_ORG_NAME},
        ).scalar()
        conn.execute(
            sa.text(
                "UPDATE workspaces SET organization_id = :org WHERE organization_id IS NULL"
            ),
            {"org": org_id},
        )
    op.alter_column("workspaces", "organization_id", nullable=False)
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    op.create_foreign_key(
        "fk_workspaces_organization_id",
        "workspaces",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_workspaces_organization_id", "workspaces", type_="foreignkey")
    op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
    op.drop_column("workspaces", "organization_id")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace_id", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
    sa.Enum(name="workspace_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
