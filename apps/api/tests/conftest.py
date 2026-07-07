import os
import tempfile
from pathlib import Path

# Must be set before any atip_api import: settings are cached at first use.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://atip:atip@127.0.0.1:5433/atip_test"
os.environ["STORAGE_DIR"] = str(Path(tempfile.mkdtemp(prefix="atip-test-")) / "uploads")
os.environ["MAX_UPLOAD_MB"] = "1"

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from atip_api import models  # noqa: F401  # register all tables on Base.metadata
from atip_api.config import get_settings
from atip_api.db import Base, get_engine
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
async def client():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
