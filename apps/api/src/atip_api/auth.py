"""Cookie-session authentication and workspace RBAC.

Design: opaque session tokens (not JWTs) in an HttpOnly, Secure,
SameSite=Strict cookie. The reverse proxy serves web and API from one origin,
so the cookie flows same-site everywhere (including EventSource for SSE chat)
and cross-origin CORS never applies. Only the SHA-256 of the token is stored;
deleting the row revokes the session instantly — no key rotation, no token
re-signing, no logout blacklist.

Tenant isolation contract:
- a workspace in another organization is answered with 404 (its existence is
  not leaked), exactly like a workspace that does not exist;
- a workspace in the caller's organization without a sufficient membership is
  403 (org_admin and platform_admin bypass memberships);
- every auth failure is logged as structured JSON with client_ip + request_id.
"""

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import anyio.to_thread
import bcrypt
from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from atip_api.config import Settings, get_settings
from atip_api.db import get_session
from atip_api.errors import AuthenticationRequiredError, ForbiddenError, NotFoundError
from atip_api.models import (
    Session,
    User,
    UserRole,
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32


# --- passwords ---


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


async def verify_password_async(password: str, password_hash: str) -> bool:
    """bcrypt is CPU-bound by design; keep it off the event loop."""
    return await anyio.to_thread.run_sync(verify_password, password, password_hash)


# --- session tokens ---


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_session(user: User, settings: Settings, request: Request) -> tuple[Session, str]:
    """Build an unsaved Session row and the raw token that goes in the cookie."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    session = Session(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        client_ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:256] or None,
    )
    return session, token


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure_effective,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure_effective,
        samesite="strict",
        path="/",
    )


# --- request authentication ---


def _client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolved X-Forwarded-For behind Caddy
    return request.client.host if request.client else "unknown"


def _auth_failure(request: Request, reason: str) -> AuthenticationRequiredError:
    logger.warning(
        "Authentication failed on %s %s: %s",
        request.method,
        request.url.path,
        reason,
        extra={"client_ip": _client_ip(request)},
    )
    return AuthenticationRequiredError("Authentication required. Log in and retry.")


async def get_current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_session)]
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _auth_failure(request, "no session cookie")

    row = (
        await db.execute(
            select(Session)
            .options(joinedload(Session.user))
            .where(Session.token_hash == hash_token(token))
        )
    ).scalar_one_or_none()
    if row is None:
        raise _auth_failure(request, "unknown session token")
    if row.expires_at <= datetime.now(UTC):
        await db.delete(row)
        await db.commit()
        raise _auth_failure(request, "session expired")
    if not row.user.is_active:
        raise _auth_failure(request, f"user {row.user.id} is deactivated")
    return row.user


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
