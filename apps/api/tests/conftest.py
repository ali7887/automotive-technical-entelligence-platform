import os
import tempfile
from pathlib import Path

# Must be set before any atip_api import: settings are cached at first use.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://atip:atip@127.0.0.1:5433/atip_test"
os.environ["STORAGE_DIR"] = str(Path(tempfile.mkdtemp(prefix="atip-test-")) / "uploads")
os.environ["MAX_UPLOAD_MB"] = "1"
# Tests must never call a real embeddings API; fakes are injected via monkeypatch.
os.environ["OPENAI_API_KEY"] = ""

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from atip_api import models  # noqa: F401  # register all tables on Base.metadata
from atip_api.auth import hash_token
from atip_api.config import get_settings
from atip_api.db import Base, get_engine, get_session_factory
from atip_api.main import create_app
from atip_api.models import Organization, Session, User, UserRole

# fixed opaque token for the default test session (only its hash is stored)
TEST_SESSION_TOKEN = "conftest-session-token"


async def _ensure_test_database() -> None:
    url = make_url(get_settings().database_url)
    admin = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="atip",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session", autouse=True)
async def _database():
    await _ensure_test_database()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(_database):
    yield
    async with get_engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def auth_user(_database) -> User:
    """Default authenticated principal: an org_admin in its own organization.

    org_admin (not member) so legacy tests keep full access to everything the
    test itself creates; RBAC boundary tests build their own users/roles.
    """
    async with get_session_factory()() as session:
        org = Organization(name="Test Org")
        session.add(org)
        await session.flush()
        user = User(
            organization_id=org.id,
            email="tester@example.com",
            password_hash="!not-a-hash",  # login is not used by the default fixture
            display_name="Tester",
            role=UserRole.ORG_ADMIN,
        )
        session.add(user)
        await session.flush()
        session.add(
            Session(
                user_id=user.id,
                token_hash=hash_token(TEST_SESSION_TOKEN),
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
        )
        await session.commit()
        return user


@pytest.fixture
async def client(auth_user):
    """Authenticated API client (the default: nearly every route needs auth)."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={get_settings().session_cookie_name: TEST_SESSION_TOKEN},
    ) as test_client:
        yield test_client


@pytest.fixture
async def anon_client(_database):
    """Unauthenticated client for auth/RBAC tests."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
