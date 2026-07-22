"""Idempotent dev seed: keep the local demo identity stable.

Ensures the demo account exists with its expected display name, so a fresh
database (or a stray rename) never breaks the demo header. Never touches an
existing password. Safe to run any number of times.

Run from apps/api so the venv and .env are picked up:

    cd apps/api
    uv run python ../../scripts/seed/dev_user.py

On first run against an empty database, set ATIP_BOOTSTRAP_PASSWORD (8-72
chars) so the user can be created; subsequent runs need no env.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from atip_api.config import get_settings
from atip_api.db import get_session_factory
from atip_api.models import Organization, User, UserRole
from atip_api.observability import configure_logging

DEMO_EMAIL = "ali.local@example.com"
DEMO_DISPLAY_NAME = "Ali"
DEMO_ORG = "Default Organization"


async def seed() -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        org = (
            await session.scalars(select(Organization).where(Organization.name == DEMO_ORG))
        ).first()
        if org is None:
            org = Organization(name=DEMO_ORG)
            session.add(org)
            await session.flush()
            print(f"created organization {DEMO_ORG!r}")

        user = (await session.scalars(select(User).where(User.email == DEMO_EMAIL))).first()
        if user is None:
            from atip_api.auth import hash_password

            password = os.environ.get("ATIP_BOOTSTRAP_PASSWORD", "")
            if len(password) < 8 or len(password) > 72:
                print("user missing: set ATIP_BOOTSTRAP_PASSWORD (8-72 chars) to create it")
                return 1
            user = User(
                organization_id=org.id,
                email=DEMO_EMAIL,
                password_hash=hash_password(password),
                display_name=DEMO_DISPLAY_NAME,
                role=UserRole.ORG_ADMIN,
            )
            session.add(user)
            print(f"created user {DEMO_EMAIL} as {DEMO_DISPLAY_NAME!r}")
        elif user.display_name != DEMO_DISPLAY_NAME:
            print(f"updated display name {user.display_name!r} -> {DEMO_DISPLAY_NAME!r}")
            user.display_name = DEMO_DISPLAY_NAME
        else:
            print(f"ok: {DEMO_EMAIL} already {DEMO_DISPLAY_NAME!r}; nothing to do")
        await session.commit()
    return 0


if __name__ == "__main__":
    configure_logging(get_settings())
    sys.exit(asyncio.run(seed()))
