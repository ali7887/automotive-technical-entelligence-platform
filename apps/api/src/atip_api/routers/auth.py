"""Auth endpoints — retained for API compatibility, authentication removed.

The platform runs open (see atip_api/auth.py): every request is the fixed
default admin. These endpoints are kept only so existing clients and the
OpenAPI contract do not break — they no longer verify credentials or manage
sessions. `/me` returns the default admin; `/login` and `/register` return it
without checking anything; `/logout` is a no-op.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import CurrentUserDep
from atip_api.db import get_session
from atip_api.schemas.auth import LoginRequest, RegisterRequest, UserRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/login", response_model=UserRead)
async def login(data: LoginRequest, user: CurrentUserDep) -> UserRead:
    """Auth disabled: returns the default admin without checking credentials."""
    return UserRead.model_validate(user)


@router.post("/register", response_model=UserRead, status_code=201)
async def register(data: RegisterRequest, user: CurrentUserDep) -> UserRead:
    """Auth disabled: signup is a no-op that returns the default admin."""
    return UserRead.model_validate(user)


@router.post("/logout", status_code=204)
async def logout() -> None:
    """Auth disabled: nothing to revoke."""
    return None


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
