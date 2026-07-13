"""Optimistic locking and extraction mutual exclusion (Phase 6 hardening)."""

import uuid

from sqlalchemy import func, select

from atip_api.config import get_settings
from atip_api.db import get_session_factory
from atip_api.errors import StaleVersionError
from atip_api.models import EvidenceItem, EvidenceRisk, EvidenceStatus
from atip_api.services.evidence import EvidenceService, _advisory_key

from .test_evidence import (
    _PHOTO_PAGES,
    _PHOTO_QUOTE,
    _PHOTO_REQUIREMENT,
    ExtractionFakeLLM,
    _create_workspace,
    _install,
    _upload_ready,
)


async def _extract_one(client, monkeypatch) -> tuple[str, str, str]:
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    payload = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    return ws_id, doc_id, payload["items"][0]["id"]


def _human(action: str, **extra) -> dict:
    return {"action": action, "actor_name": "ali", "actor_type": "HUMAN", **extra}


# --- expected_version (client-side optimistic locking) ----------------------


async def test_version_starts_at_one_and_increments(client, monkeypatch):
    ws_id, _, item_id = await _extract_one(client, monkeypatch)
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["version"] == 1

    response = await client.post(
        f"/api/evidence/{item_id}/review", json=_human("START_REVIEW")
    )
    assert response.status_code == 200
    assert response.json()["item"]["version"] == 2

    patched = await client.patch(f"/api/evidence/{item_id}", json={"risk": "HIGH"})
    assert patched.json()["version"] == 3

    queue = (await client.get(f"/api/evidence/review-queue?workspace_id={ws_id}")).json()
    assert queue["items"][0]["version"] == 3


async def test_review_with_stale_expected_version_is_409_and_writes_nothing(
    client, monkeypatch
):
    _, _, item_id = await _extract_one(client, monkeypatch)

    ok = await client.post(
        f"/api/evidence/{item_id}/review",
        json=_human("START_REVIEW", expected_version=1),
    )
    assert ok.status_code == 200

    # a second reviewer still holding version 1 loses the race, cleanly
    stale = await client.post(
        f"/api/evidence/{item_id}/review",
        json=_human("APPROVE", expected_version=1),
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "stale_version"
    assert body["type"] == "/errors/stale_version"

    history = (await client.get(f"/api/evidence/{item_id}/history")).json()
    assert [event["action"] for event in history] == ["START_REVIEW"]
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["review_status"] == "IN_REVIEW"


async def test_patch_with_stale_expected_version_is_409(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)

    first = await client.patch(
        f"/api/evidence/{item_id}", json={"risk": "HIGH", "expected_version": 1}
    )
    assert first.status_code == 200

    second = await client.patch(
        f"/api/evidence/{item_id}", json={"risk": "LOW", "expected_version": 1}
    )
    assert second.status_code == 409
    assert second.json()["code"] == "stale_version"
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["risk"] == "HIGH"


# --- StaleDataError translation (database-level race) ------------------------


async def test_lost_update_race_raises_409_not_silent_overwrite(client, monkeypatch):
    """Two sessions load the same item; the slower commit must 409, not clobber."""
    _, _, item_id = await _extract_one(client, monkeypatch)
    factory = get_session_factory()
    settings = get_settings()

    async with factory() as session_a, factory() as session_b:
        item_a = await session_a.get(EvidenceItem, uuid.UUID(item_id))
        item_b = await session_b.get(EvidenceItem, uuid.UUID(item_id))
        assert item_a is not None and item_b is not None

        item_a.risk = EvidenceRisk.HIGH
        await EvidenceService(session_a, settings)._commit_versioned()

        item_b.status = EvidenceStatus.COMPLIANT
        try:
            await EvidenceService(session_b, settings)._commit_versioned()
            raise AssertionError("expected StaleVersionError")
        except StaleVersionError:
            pass

    # the winner's write survived; the loser's was rolled back
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["risk"] == "HIGH"
    assert detail["status"] == "OPEN"
    assert detail["version"] == 2


# --- extraction mutual exclusion ---------------------------------------------


async def test_extract_is_blocked_while_another_extraction_holds_the_lock(
    client, monkeypatch
):
    _, doc_id, _ = await _extract_one(client, monkeypatch)

    factory = get_session_factory()
    async with factory() as blocker:
        # simulate a running extraction: hold the same advisory lock in an open tx
        await blocker.execute(
            select(func.pg_advisory_xact_lock(_advisory_key(uuid.UUID(doc_id))))
        )
        response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
        assert response.status_code == 409
        assert response.json()["code"] == "extraction_in_progress"
        await blocker.rollback()

    # once the lock is released, extraction works again
    response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert response.status_code == 201
