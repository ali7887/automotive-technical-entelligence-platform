"""Dependency-failure resilience: retries, fallbacks, and 503 mapping (Phase 6)."""

from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from openai import APIConnectionError
from sqlalchemy.exc import OperationalError

from atip_api.ai.embeddings import OpenAIEmbeddingClient
from atip_api.ai.llm import OpenAIChatClient
from atip_api.main import create_app
from atip_api.resilience import db_retrying, openai_retrying

from .pdf_utils import pdf_with_text


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "http://llm.test"))


class _Flaky:
    """Callable failing `failures` times before delegating to `result`."""

    def __init__(self, failures: int, result):
        self.failures = failures
        self.calls = 0
        self._result = result

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise _connection_error()
        return self._result() if callable(self._result) else self._result


# --- retry policies -----------------------------------------------------------


async def test_openai_retrying_recovers_from_transient_failures():
    flaky = _Flaky(failures=2, result="ok")
    outcome = None
    async for attempt in openai_retrying():
        with attempt:
            outcome = await flaky()
    assert outcome == "ok"
    assert flaky.calls == 3  # 2 failures + 1 success = the 3-attempt budget


async def test_openai_retrying_gives_up_after_three_attempts():
    flaky = _Flaky(failures=10, result="never")
    with pytest.raises(APIConnectionError):
        async for attempt in openai_retrying():
            with attempt:
                await flaky()
    assert flaky.calls == 3


async def test_non_transient_errors_are_not_retried():
    calls = 0

    async def broken():
        nonlocal calls
        calls += 1
        raise ValueError("a bug, not an outage")

    with pytest.raises(ValueError):
        async for attempt in openai_retrying():
            with attempt:
                await broken()
    assert calls == 1


async def test_db_retrying_retries_operational_errors():
    calls = 0

    async def flaky_connect():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OperationalError("SELECT 1", None, Exception("connection refused"))
        return "connected"

    outcome = None
    async for attempt in db_retrying():
        with attempt:
            outcome = await flaky_connect()
    assert outcome == "connected"
    assert calls == 3


# --- clients retry through the policy ------------------------------------------


def _embedding_response(vectors: list[list[float]]):
    return SimpleNamespace(
        data=[SimpleNamespace(index=i, embedding=v) for i, v in enumerate(vectors)]
    )


async def test_embedding_client_retries_batches():
    client = OpenAIEmbeddingClient(
        api_key="test", model="m", dimensions=3, base_url=None, timeout=5.0
    )
    flaky = _Flaky(failures=2, result=lambda: _embedding_response([[1.0, 2.0, 3.0]]))
    fake_sdk = SimpleNamespace(embeddings=SimpleNamespace(create=flaky))
    object.__setattr__(client, "_client", fake_sdk)  # stand-in for the OpenAI SDK

    vectors = await client.embed(["hello"])
    assert vectors == [[1.0, 2.0, 3.0]]
    assert flaky.calls == 3


async def _fake_stream_events():
    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="veri"))])
    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="fied"))])


async def test_llm_client_retries_stream_establishment():
    client = OpenAIChatClient(api_key="test", model="m", base_url=None, timeout=5.0)
    flaky = _Flaky(failures=1, result=_fake_stream_events)
    fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=flaky)))
    object.__setattr__(client, "_client", fake_sdk)  # stand-in for the OpenAI SDK

    parts = [delta async for delta in client.stream(system="s", user="u")]
    assert "".join(parts) == "verified"
    assert flaky.calls == 2


# --- graceful degradation -------------------------------------------------------


class _AlwaysFailingEmbeddings:
    async def embed(self, texts):
        raise _connection_error()


async def test_search_falls_back_to_keyword_when_embeddings_are_down(client, monkeypatch):
    """LLM/embedding provider down => hybrid search degrades, never 500s."""
    monkeypatch.setattr(
        "atip_api.ai.embeddings.get_embedding_client", lambda s: _AlwaysFailingEmbeddings()
    )
    ws_id = (await client.post("/api/workspaces", json={"name": "Chaos"})).json()["id"]
    page = "S5.1 Each headlamp shall conform to the photometric requirements of Table XIX."
    upload = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("r.pdf", pdf_with_text([page]), "application/pdf")},
    )
    assert upload.status_code == 202

    response = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "photometric requirements"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["semantic_used"] is False
    assert body["results"], "keyword leg must still return results"


async def test_database_outage_maps_to_503_problem():
    app = create_app()

    @app.get("/api/_test/db-down")
    async def db_down():  # pyright: ignore[reportUnusedFunction]
        raise OperationalError("SELECT 1", None, Exception("server closed the connection"))

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.get("/api/_test/db-down")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "service_unavailable"
    assert body["type"] == "/errors/service_unavailable"
    assert response.headers["retry-after"] == "5"
    # internals (driver message) are not leaked
    assert "server closed" not in body["detail"]
