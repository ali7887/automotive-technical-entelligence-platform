"""Auth-free principal resolution and workspace RBAC.

Authentication has been removed: the platform runs open, and every request is
treated as a single fixed **default admin** (a PLATFORM_ADMIN). `get_current_user`
no longer inspects any cookie or session — it lazily ensures and returns that
one account, so all callers (routers, workspace authorization) keep their exact
signatures. Because the principal is a PLATFORM_ADMIN, `authorize_workspace` and
`accessible_workspace_ids` grant unrestricted access; the org/user model is kept
intact so auth can be reinstated later by restoring cookie validation here.

The workspace-role machinery below is unchanged and still enforced in principle;
it is simply always satisfied by the admin principal.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from atip_api.db import get_session
from atip_api.errors import ForbiddenError, NotFoundError
from atip_api.models import (
    Organization,
    User,
    UserRole,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)

logger = logging.getLogger(__name__)

# The single principal every request runs as, now that auth is disabled.
DEFAULT_ADMIN_EMAIL = "admin@atip.local"
DEFAULT_ADMIN_NAME = "Ali Kiani"
DEFAULT_ORG_NAME = "Default Organization"
# Login is gone, so this hash can never match anything — it is a placeholder.
_UNUSABLE_PASSWORD_HASH = "!auth-disabled"


# --- passwords ---


def hash_password(password: str) -> str:
    """Retained for account-seeding scripts/CLI; unused by request handling."""
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


# --- request principal (auth removed) ---


def _client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolved X-Forwarded-For behind Caddy
    return request.client.host if request.client else "unknown"


async def ensure_default_admin(db: AsyncSession) -> User:
    """Lazily create (once) and return the fixed default-admin principal.

    Idempotent: the org and user are keyed by their stable names, so concurrent
    first requests converge on the same rows. The organization is eager-loaded
    because UserRead needs it.
    """
    user = (
        await db.execute(
            select(User)
            .options(joinedload(User.organization))
            .where(User.email == DEFAULT_ADMIN_EMAIL)
        )
    ).scalar_one_or_none()
    if user is not None:
        return user

    org = (
        await db.execute(select(Organization).where(Organization.name == DEFAULT_ORG_NAME))
    ).scalar_one_or_none()
    if org is None:
        org = Organization(name=DEFAULT_ORG_NAME)
        db.add(org)
        await db.flush()

    user = User(
        organization_id=org.id,
        email=DEFAULT_ADMIN_EMAIL,
        password_hash=_UNUSABLE_PASSWORD_HASH,
        display_name=DEFAULT_ADMIN_NAME,
        role=UserRole.PLATFORM_ADMIN,
    )
    db.add(user)
    await db.commit()
    # reload with the organization relationship populated
    return (
        await db.execute(
            select(User)
            .options(joinedload(User.organization))
            .where(User.id == user.id)
        )
    ).scalar_one()


async def get_current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> User:
    """Auth is disabled: every request runs as the fixed default admin."""
    return await ensure_default_admin(db)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# --- workspace authorization ---


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    user: User


async def authorize_workspace(
    db: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    minimum: WorkspaceRole,
    *,
    request: Request | None = None,
) -> Workspace:
    """Return the workspace iff the user may act on it at `minimum` role."""
    workspace = await db.get(Workspace, workspace_id)
    in_org = workspace is not None and workspace.organization_id == user.organization_id
    if workspace is None or (not in_org and user.role != UserRole.PLATFORM_ADMIN):
        # cross-tenant probes look identical to missing workspaces
        _log_denied(request, user, workspace_id, "not found or foreign organization")
        raise NotFoundError(f"Workspace {workspace_id} not found")
    if user.role in (UserRole.PLATFORM_ADMIN, UserRole.ORG_ADMIN):
        return workspace

    membership = (
        await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        _log_denied(request, user, workspace_id, "no membership")
        raise ForbiddenError("You are not a member of this workspace.")
    if (
        minimum == WorkspaceRole.WORKSPACE_EDITOR
        and membership.role != WorkspaceRole.WORKSPACE_EDITOR
    ):
        _log_denied(request, user, workspace_id, "viewer role, editor required")
        raise ForbiddenError("This action requires editor access to the workspace.")
    return workspace


def _log_denied(
    request: Request | None, user: User, workspace_id: uuid.UUID, reason: str
) -> None:
    logger.warning(
        "Workspace access denied: user=%s workspace=%s (%s)",
        user.id,
        workspace_id,
        reason,
        extra={"client_ip": _client_ip(request)} if request else None,
    )


async def accessible_workspace_ids(
    db: AsyncSession, user: User
) -> list[uuid.UUID] | None:
    """Workspace ids the user may read; None means unrestricted (platform_admin)."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return None
    if user.role == UserRole.ORG_ADMIN:
        rows = await db.scalars(
            select(Workspace.id).where(Workspace.organization_id == user.organization_id)
        )
        return list(rows)
    rows = await db.scalars(
        select(WorkspaceMember.workspace_id)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == user.id,
            Workspace.organization_id == user.organization_id,
        )
    )
    return list(rows)


def require_workspace(minimum: WorkspaceRole):
    """Path dependency for routes with a `workspace_id` path parameter."""

    async def dependency(
        workspace_id: uuid.UUID,
        request: Request,
        user: CurrentUserDep,
        db: Annotated[AsyncSession, Depends(get_session)],
    ) -> WorkspaceAccess:
        workspace = await authorize_workspace(db, user, workspace_id, minimum, request=request)
        return WorkspaceAccess(workspace=workspace, user=user)

    return dependency


WorkspaceViewerDep = Annotated[
    WorkspaceAccess, Depends(require_workspace(WorkspaceRole.WORKSPACE_VIEWER))
]
WorkspaceEditorDep = Annotated[
    WorkspaceAccess, Depends(require_workspace(WorkspaceRole.WORKSPACE_EDITOR))
]
