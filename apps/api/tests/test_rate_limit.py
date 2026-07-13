"""Rate limiting on /ask, /chat, and evidence extraction (Phase 6)."""

import uuid

from atip_api.config import get_settings
from atip_api.ratelimit import SlidingWindowRateLimiter

from .test_evidence import (
    _PHOTO_PAGES,
    _PHOTO_QUOTE,
    _PHOTO_REQUIREMENT,
    ExtractionFakeLLM,
    _create_workspace,
    _install,
    _upload_ready,
)

_QUESTION = "What is the photometric limit?"


async def _ask(client, ws_id: str):
    return await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})


async def test_ask_over_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_ask_per_minute", 2)
    ws_id = await _create_workspace(client)

    # no API key configured: allowed calls hit the 503 in the handler itself
    assert (await _ask(client, ws_id)).status_code == 503
    assert (await _ask(client, ws_id)).status_code == 503

    limited = await _ask(client, ws_id)
    assert limited.status_code == 429
    body = limited.json()
    assert body["code"] == "rate_limited"
    assert body["type"] == "/errors/rate_limited"
    retry_after = int(limited.headers["retry-after"])
    assert 1 <= retry_after <= 60


async def test_chat_shares_the_ask_budget(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_ask_per_minute", 1)
    ws_id = await _create_workspace(client)

    assert (await _ask(client, ws_id)).status_code == 503
    limited = await client.get(
        f"/api/workspaces/{ws_id}/chat", params={"question": _QUESTION}
    )
    assert limited.status_code == 429
    assert "retry-after" in limited.headers


async def test_extract_over_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_extract_per_minute", 1)
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    assert (await client.post(f"/api/documents/{doc_id}/evidence/extract")).status_code == 201
    limited = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert "retry-after" in limited.headers


async def test_rate_limiting_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    monkeypatch.setattr(get_settings(), "rate_limit_ask_per_minute", 1)
    ws_id = await _create_workspace(client)
    for _ in range(3):
        assert (await _ask(client, ws_id)).status_code == 503


async def test_limits_are_per_bucket(client, monkeypatch):
    # exhausting the ask budget must not block unrelated endpoints
    monkeypatch.setattr(get_settings(), "rate_limit_ask_per_minute", 1)
    ws_id = await _create_workspace(client)
    assert (await _ask(client, ws_id)).status_code == 503
    assert (await _ask(client, ws_id)).status_code == 429
    assert (await client.get(f"/api/workspaces/{uuid.UUID(ws_id)}")).status_code == 200


def test_sliding_window_math():
    limiter = SlidingWindowRateLimiter(window_seconds=60.0)
    assert limiter.check("k", 2, now=0.0) is None
    assert limiter.check("k", 2, now=10.0) is None
    # third hit within the window: blocked until the oldest hit ages out
    assert limiter.check("k", 2, now=30.0) == 30
    assert limiter.check("k", 2, now=59.9) == 1
    # oldest hit (t=0) has aged out at t=60; one slot frees up
    assert limiter.check("k", 2, now=60.5) is None
    # separate keys have separate budgets
    assert limiter.check("other", 2, now=60.5) is None
