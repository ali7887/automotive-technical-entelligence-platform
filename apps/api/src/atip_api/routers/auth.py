"""Login / logout / session introspection.

Login is rate limited per client IP (credential stuffing) and failures are
logged as structured JSON with client_ip + request_id. The cookie is HttpOnly,
SameSite=Strict, and Secure in production; see atip_api/auth.py for the
session model.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from atip_api.auth import (
    CurrentUserDep,
    clear_session_cookie,
    hash_token,
    new_session,
    set_session_cookie,
    verify_password_async,
)
from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.errors import InvalidCredentialsError
from atip_api.models import Session, User
from atip_api.ratelimit import rate_limited
from atip_api.schemas.auth import LoginRequest, UserRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOGIN_LIMIT = rate_limited("login", lambda settings: settings.rate_limit_login_per_minute)

DbDep = Annotated[AsyncSession, Depends(get_session)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserRead, dependencies=[_LOGIN_LIMIT])
async def login(
    data: LoginRequest, request: Request, response: Response, db: DbDep
) -> UserRead:
    settings = get_settings()
    user = (
        await db.execute(
            select(User)
            .options(joinedload(User.organization))
            .where(User.email == data.email.lower())
        )
    ).scalar_one_or_none()

    # constant-shape failure: same error for unknown email / bad password /
    # deactivated account, so accounts cannot be enumerated
    password_ok = user is not None and await verify_password_async(
        data.password, user.password_hash
    )
    if user is None or not password_ok or not user.is_active:
        logger.warning(
            "Login failed for %s: %s",
            data.email.lower(),
            "unknown user"
            if user is None
            else ("bad password" if not password_ok else "deactivated"),
            extra={"client_ip": _client_ip(request)},
        )
        raise InvalidCredentialsError("Email or password is incorrect.")

    session, token = new_session(user, settings, request)
    db.add(session)
    await db.commit()
    set_session_cookie(response, settings, token)
    logger.info(
        "Login succeeded for user %s", user.id, extra={"client_ip": _client_ip(request)}
    )
    return UserRead.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DbDep) -> None:
    """Revoke the presented session (idempotent: no error without one)."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await db.execute(delete(Session).where(Session.token_hash == hash_token(token)))
        await db.commit()
    clear_session_cookie(response, settings)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep, db: DbDep) -> UserRead:
    # the dependency loaded the user; organization is needed by the response
    loaded = (
        await db.execute(
            select(User).options(joinedload(User.organization)).where(User.id == user.id)
        )
    ).scalar_one()
    return UserRead.model_validate(loaded)
