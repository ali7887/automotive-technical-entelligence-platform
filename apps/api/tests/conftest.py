import os
import tempfile
from pathlib import Path

# Must be set before any atip_api import: settings are cached at first use.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://atip:atip@127.0.0.1:5433/atip_test"
os.environ["STORAGE_DIR"] = str(Path(tempfile.mkdtemp(prefix="atip-test-")) / "uploads")
os.environ["MAX_UPLOAD_MB"] = "1"
# Tests must never call a real embeddings API; fakes are injected via monkeypatch.
os.environ["OPENAI_API_KEY"] = ""

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from atip_api import models  # noqa: F401  # register all tables on Base.metadata
from atip_api.auth import ensure_default_admin
from atip_api.config import get_settings
from atip_api.db import Base, get_engine, get_session_factory
from atip_api.main import create_app


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
async def auth_user(_database):
    """The request principal. Auth is removed, so every request resolves to the
    fixed default admin; tests seed their data under this same account/org."""
    async with get_session_factory()() as session:
        user = await ensure_default_admin(session)
        return user


@pytest.fixture
async def client(auth_user):
    """API client. Auth is disabled — no cookie needed; every request runs as
    the default admin (the same principal `auth_user` returns)."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def anon_client(_database):
    """Alias of `client` now that auth is removed (kept for existing tests)."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
