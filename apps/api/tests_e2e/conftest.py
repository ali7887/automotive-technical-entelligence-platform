"""Release-smoke E2E suite: runs against a LIVE API over real HTTP.

Not part of the default pytest run (testpaths only covers tests/). Usage:

    uv run uvicorn atip_api.main:app --port 8000   # + migrated DB, services up
    uv run pytest tests_e2e -q                     # ATIP_E2E_BASE_URL to override

Every check is deterministic and LLM-free: no test depends on OpenAI being
configured, so the suite is safe to run against any deployment.
"""

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

BASE_URL = os.environ.get("ATIP_E2E_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as http:
        try:
            response = await http.get("/health/live")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.fail(
                f"No live API at {BASE_URL} ({exc!r}). Start it first or set "
                "ATIP_E2E_BASE_URL — see the module docstring.",
                pytrace=False,
            )
        yield http


@pytest.fixture
async def workspace(client: httpx.AsyncClient) -> AsyncIterator[dict]:
    response = await client.post(
        "/api/workspaces", json={"name": f"e2e-smoke-{uuid.uuid4().hex[:8]}"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    yield body
    await client.delete(f"/api/workspaces/{body['id']}")
