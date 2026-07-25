"""Public self-service registration.

A signup creates a brand-new Organization and the registrant becomes its
ORG_ADMIN, so every account is its own isolated tenant. Org admins bypass
workspace memberships within their own org (see atip_api.auth), so a fresh
account can create and use workspaces immediately without any extra grant.

Deliberately out of scope for this pass (see the register endpoint / docs):
- email verification: accounts are active on creation, no email is sent;
- inviting additional users into an existing organization.

Password hashing reuses the shared bcrypt helpers; the request-shape and
password-policy validation live in atip_api.schemas.auth.RegisterRequest.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import hash_password
from atip_api.errors import EmailAlreadyRegisteredError, OrganizationExistsError
from atip_api.models import Organization, User, UserRole

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """The `users.email` column stores the lowercased, trimmed address."""
    return email.strip().lower()


async def register_account(
    db: AsyncSession,
    *,
    display_name: str,
    email: str,
    organization_name: str,
    password: str,
) -> User:
    """Create {Organization, User(ORG_ADMIN)} atomically and return the user.

    The caller owns the surrounding transaction (it also creates the session
    row): this only flushes. The friendly pre-checks below give clear errors
    for the common case; the unique constraints on `users.email` and
    `organizations.name` are the real, race-safe guard — a signup that loses
    the race to a concurrent one surfaces the same 409, never a 500.
    """
    email = normalize_email(email)
    organization_name = organization_name.strip()
    display_name = display_name.strip()

    if await _email_taken(db, email):
        raise EmailAlreadyRegisteredError(
            "An account with this email already exists. Try signing in instead."
        )
    org_exists = (
        await db.execute(
            select(Organization.id).where(
                func.lower(Organization.name) == organization_name.lower()
            )
        )
    ).first()
    if org_exists is not None:
        raise OrganizationExistsError(
            "An organization with this name already exists. "
            "If this is your company, ask an administrator to invite you."
        )

    org = Organization(name=organization_name)
    user = User(
        organization=org,  # in-memory link so UserRead needs no extra query
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        role=UserRole.ORG_ADMIN,
    )
    db.add(org)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # Lost the race between the pre-check and the unique index. Re-query to
        # attribute the collision correctly without parsing driver error text.
        if await _email_taken(db, email):
            raise EmailAlreadyRegisteredError(
                "An account with this email already exists. Try signing in instead."
            ) from exc
        raise OrganizationExistsError(
            "An organization with this name already exists. "
            "If this is your company, ask an administrator to invite you."
        ) from exc

    logger.info("Registered user %s (org %s) as org_admin", user.id, org.id)
    return user


async def _email_taken(db: AsyncSession, email: str) -> bool:
    return (
        await db.execute(select(User.id).where(User.email == email))
    ).first() is not None
