"""Release-smoke E2E suite: runs against a LIVE API over real HTTP.

Not part of the default pytest run (testpaths only covers tests/). Usage:

    uv run uvicorn atip_api.main:app --port 8000   # + migrated DB, services up
    ATIP_BOOTSTRAP_PASSWORD=e2e-smoke-password uv run python -m atip_api.cli \
        create-user --email e2e@atip.local --org "E2E Smoke" --role org_admin
    uv run pytest tests_e2e -q                     # ATIP_E2E_BASE_URL to override

Every check is deterministic and LLM-free: no test depends on OpenAI being
configured, so the suite is safe to run against any deployment. All routes
except /health require auth, so the suite logs in first; point
ATIP_E2E_EMAIL / ATIP_E2E_PASSWORD at an existing account.
"""

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

BASE_URL = os.environ.get("ATIP_E2E_BASE_URL", "http://127.0.0.1:8000")
E2E_EMAIL = os.environ.get("ATIP_E2E_EMAIL", "e2e@atip.local")
E2E_PASSWORD = os.environ.get("ATIP_E2E_PASSWORD", "e2e-smoke-password")


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
        login = await http.post(
            "/api/auth/login", json={"email": E2E_EMAIL, "password": E2E_PASSWORD}
        )
        if login.status_code != 200:
            pytest.fail(
                f"Login as {E2E_EMAIL} failed ({login.status_code}). Create the "
                "account first (see the module docstring) or set "
                "ATIP_E2E_EMAIL / ATIP_E2E_PASSWORD.",
                pytrace=False,
            )
        # the session cookie persists on the client for the whole suite
        yield http
        await http.post("/api/auth/logout")


@pytest.fixture
async def workspace(client: httpx.AsyncClient) -> AsyncIterator[dict]:
    response = await client.post(
        "/api/workspaces", json={"name": f"e2e-smoke-{uuid.uuid4().hex[:8]}"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    yield body
    await client.delete(f"/api/workspaces/{body['id']}")
