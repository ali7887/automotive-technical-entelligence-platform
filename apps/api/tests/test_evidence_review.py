"""Integration tests for the Phase 5 review workflow and audit trail."""

import uuid

from .test_evidence import (
    _FILLER,
    _PHOTO_PAGES,
    _PHOTO_QUOTE,
    _PHOTO_REQUIREMENT,
    ExtractionFakeLLM,
    _create_workspace,
    _install,
    _upload_ready,
)

_BRAKE_QUOTE = "The service brake system shall stop the vehicle within 70 metres from 100 km/h."
_BRAKE_REQUIREMENT = "Service brakes must stop the vehicle within 70 m from 100 km/h."

_TWO_REQ_PAGES = [
    "\n".join(["S5.1.2 Photometric requirements", _PHOTO_QUOTE, *[_FILLER] * 6]),
    "\n".join(["S5.3 Braking requirements", _BRAKE_QUOTE, *[_FILLER] * 6]),
]


def _human(action: str, **extra) -> dict:
    return {"action": action, "actor_name": "ali", "actor_type": "HUMAN", **extra}


async def _extract_one(client, monkeypatch) -> tuple[str, str, str]:
    """Workspace with one document and one extracted item; returns their ids."""
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    payload = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    return ws_id, doc_id, payload["items"][0]["id"]


async def _review(client, item_id: str, action: str, **extra):
    return await client.post(f"/api/evidence/{item_id}/review", json=_human(action, **extra))


# --- state machine ---------------------------------------------------------


async def test_full_happy_path_start_then_approve(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)

    started = await _review(client, item_id, "START_REVIEW")
    assert started.status_code == 200
    assert started.json()["item"]["review_status"] == "IN_REVIEW"
    event = started.json()["event"]
    assert event["action"] == "START_REVIEW"
    assert event["previous_status"] == "NEW"
    assert event["next_status"] == "IN_REVIEW"
    assert event["actor_name"] == "ali"

    approved = await _review(client, item_id, "APPROVE")
    assert approved.status_code == 200
    assert approved.json()["item"]["review_status"] == "APPROVED"


async def test_decisions_require_in_review(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    for action, extra in (
        ("APPROVE", {}),
        ("REJECT", {"comment": "bad extraction"}),
        ("REQUEST_REVISION", {"comment": "please recheck"}),
    ):
        response = await _review(client, item_id, action, **extra)
        assert response.status_code == 409, action
        assert response.json()["code"] == "invalid_review_transition"


async def test_start_review_not_allowed_while_in_review(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "START_REVIEW")
    response = await _review(client, item_id, "START_REVIEW")
    assert response.status_code == 409


async def test_decided_item_can_be_reopened(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "START_REVIEW")
    await _review(client, item_id, "REJECT", comment="wrong clause")

    reopened = await _review(client, item_id, "START_REVIEW")
    assert reopened.status_code == 200
    assert reopened.json()["item"]["review_status"] == "IN_REVIEW"

    revised = await _review(client, item_id, "REQUEST_REVISION", comment="tighten wording")
    assert revised.json()["item"]["review_status"] == "NEEDS_REVISION"
    assert (await _review(client, item_id, "START_REVIEW")).status_code == 200


async def test_reject_and_revision_require_comment(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "START_REVIEW")
    for action in ("REJECT", "REQUEST_REVISION"):
        assert (await _review(client, item_id, action)).status_code == 422
        assert (await _review(client, item_id, action, comment="   ")).status_code == 422


async def test_comment_keeps_status_and_requires_text(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    assert (await _review(client, item_id, "COMMENT")).status_code == 422

    response = await _review(client, item_id, "COMMENT", comment="checked against ECE R13")
    assert response.status_code == 200
    assert response.json()["item"]["review_status"] == "NEW"
    assert response.json()["event"]["comment"] == "checked against ECE R13"


async def test_set_risk_updates_risk_without_status_change(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    assert (await _review(client, item_id, "SET_RISK")).status_code == 422
    # risk payload is rejected on any other action
    assert (await _review(client, item_id, "START_REVIEW", risk="HIGH")).status_code == 422

    response = await _review(client, item_id, "SET_RISK", risk="HIGH")
    assert response.status_code == 200
    assert response.json()["item"]["risk"] == "HIGH"
    assert response.json()["item"]["review_status"] == "NEW"
    event = response.json()["event"]
    assert event["previous_risk"] == "UNRATED"
    assert event["next_risk"] == "HIGH"


async def test_system_only_actions_cannot_be_submitted(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    for action in ("SET_STATUS", "EXTRACTION_ARCHIVED"):
        assert (await _review(client, item_id, action)).status_code == 422


async def test_review_missing_item_returns_404(client):
    response = await client.post(
        f"/api/evidence/{uuid.uuid4()}/review", json=_human("START_REVIEW")
    )
    assert response.status_code == 404


# --- audit trail ------------------------------------------------------------


async def test_history_is_ordered_and_complete(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "SET_RISK", risk="MEDIUM")
    await _review(client, item_id, "START_REVIEW")
    await _review(client, item_id, "COMMENT", comment="looks plausible")
    await _review(client, item_id, "APPROVE")

    history = (await client.get(f"/api/evidence/{item_id}/history")).json()
    assert [event["action"] for event in history] == [
        "SET_RISK",
        "START_REVIEW",
        "COMMENT",
        "APPROVE",
    ]
    # each event chains from the previous snapshot
    assert history[1]["previous_status"] == "NEW"
    assert history[1]["next_status"] == "IN_REVIEW"
    assert history[3]["previous_status"] == "IN_REVIEW"
    assert history[3]["next_status"] == "APPROVED"
    assert all(event["evidence_item_id"] == item_id for event in history)


async def test_rejected_transition_writes_nothing(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    assert (await _review(client, item_id, "APPROVE")).status_code == 409
    assert (await client.get(f"/api/evidence/{item_id}/history")).json() == []
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["review_status"] == "NEW"


async def test_patch_edits_are_audited_and_cannot_touch_review_status(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    response = await client.patch(
        f"/api/evidence/{item_id}",
        json={"status": "COMPLIANT", "risk": "LOW", "actor_name": "ali"},
    )
    assert response.status_code == 200
    assert response.json()["review_status"] == "NEW"

    history = (await client.get(f"/api/evidence/{item_id}/history")).json()
    assert [event["action"] for event in history] == ["SET_STATUS", "SET_RISK"]
    set_status = history[0]
    assert set_status["extra"] == {"field": "status", "previous": "OPEN", "next": "COMPLIANT"}
    assert set_status["previous_status"] == set_status["next_status"] == "NEW"
    assert history[1]["next_risk"] == "LOW"

    # a no-op PATCH appends nothing
    await client.patch(f"/api/evidence/{item_id}", json={"status": "COMPLIANT"})
    assert len((await client.get(f"/api/evidence/{item_id}/history")).json()) == 2


async def test_history_missing_item_returns_404(client):
    assert (await client.get(f"/api/evidence/{uuid.uuid4()}/history")).status_code == 404


# --- detail -----------------------------------------------------------------


async def test_detail_includes_citations_and_last_event(client, monkeypatch):
    _, _, item_id = await _extract_one(client, monkeypatch)
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["event_count"] == 0
    assert detail["last_event"] is None
    assert len(detail["citations"]) == 1

    await _review(client, item_id, "START_REVIEW")
    detail = (await client.get(f"/api/evidence/{item_id}")).json()
    assert detail["event_count"] == 1
    assert detail["last_event"]["action"] == "START_REVIEW"
    assert detail["review_status"] == "IN_REVIEW"


async def test_detail_missing_item_returns_404(client):
    assert (await client.get(f"/api/evidence/{uuid.uuid4()}")).status_code == 404


# --- review queue -----------------------------------------------------------


async def _extract_two(client, monkeypatch) -> tuple[str, str, list[dict]]:
    _install(
        monkeypatch,
        ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE), (_BRAKE_REQUIREMENT, _BRAKE_QUOTE)]),
    )
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _TWO_REQ_PAGES, "fmvss.pdf")
    items = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()["items"]
    assert len(items) == 2
    return ws_id, doc_id, items


async def test_queue_filters_by_review_status_and_risk(client, monkeypatch):
    ws_id, _, items = await _extract_two(client, monkeypatch)
    await _review(client, items[0]["id"], "START_REVIEW")
    await _review(client, items[1]["id"], "SET_RISK", risk="HIGH")

    queue = (await client.get("/api/evidence/review-queue")).json()
    assert queue["total"] == 2
    row = queue["items"][0]
    assert {"citation_count", "document_name", "review_status"} <= row.keys()

    in_review = (
        await client.get("/api/evidence/review-queue", params={"review_status": "IN_REVIEW"})
    ).json()
    assert in_review["total"] == 1
    assert in_review["items"][0]["id"] == items[0]["id"]

    high = (await client.get("/api/evidence/review-queue", params={"risk": "HIGH"})).json()
    assert high["total"] == 1
    assert high["items"][0]["id"] == items[1]["id"]

    scoped = (
        await client.get("/api/evidence/review-queue", params={"workspace_id": str(uuid.uuid4())})
    ).json()
    assert scoped["total"] == 0
    assert (await client.get("/api/evidence/review-queue", params={"workspace_id": ws_id})).json()[
        "total"
    ] == 2


async def test_queue_pagination_and_risk_sort(client, monkeypatch):
    _, _, items = await _extract_two(client, monkeypatch)
    await _review(client, items[1]["id"], "SET_RISK", risk="HIGH")

    page = (
        await client.get(
            "/api/evidence/review-queue", params={"sort": "risk_desc", "limit": 1, "offset": 0}
        )
    ).json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == items[1]["id"]  # HIGH sorts above UNRATED

    second = (
        await client.get(
            "/api/evidence/review-queue", params={"sort": "risk_desc", "limit": 1, "offset": 1}
        )
    ).json()
    assert second["items"][0]["id"] == items[0]["id"]

    assert (await client.get("/api/evidence/review-queue", params={"limit": 0})).status_code == 422
    assert (
        await client.get("/api/evidence/review-queue", params={"sort": "nonsense"})
    ).status_code == 422


# --- re-extraction lifecycle -------------------------------------------------


async def test_reextraction_archives_reviewed_items(client, monkeypatch):
    ws_id, doc_id, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "START_REVIEW")
    await _review(client, item_id, "APPROVE")

    second = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    assert second["items_archived"] == 1
    assert any("archived" in warning for warning in second["warnings"])
    new_item_id = second["items"][0]["id"]
    assert new_item_id != item_id

    # the archived item survives with citations and full history plus a system event
    archived = (await client.get(f"/api/evidence/{item_id}")).json()
    assert archived["archived_at"] is not None
    assert archived["review_status"] == "APPROVED"
    assert len(archived["citations"]) == 1
    history = (await client.get(f"/api/evidence/{item_id}/history")).json()
    assert [event["action"] for event in history] == [
        "START_REVIEW",
        "APPROVE",
        "EXTRACTION_ARCHIVED",
    ]
    assert history[-1]["actor_type"] == "SYSTEM"

    # archived items leave the queue and the workspace list unless requested
    queue = (await client.get("/api/evidence/review-queue")).json()
    assert [row["id"] for row in queue["items"]] == [new_item_id]
    with_archived = (
        await client.get("/api/evidence/review-queue", params={"include_archived": "true"})
    ).json()
    assert with_archived["total"] == 2
    listed = (await client.get(f"/api/workspaces/{ws_id}/evidence")).json()
    assert [entry["id"] for entry in listed] == [new_item_id]


async def test_archived_item_is_read_only(client, monkeypatch):
    _, doc_id, item_id = await _extract_one(client, monkeypatch)
    await _review(client, item_id, "START_REVIEW")
    await client.post(f"/api/documents/{doc_id}/evidence/extract")

    response = await _review(client, item_id, "START_REVIEW")
    assert response.status_code == 409
    assert "archived" in response.json()["message"]


# --- export metadata ----------------------------------------------------------


async def test_export_carries_review_metadata_and_history(client, monkeypatch):
    ws_id, _, items = await _extract_two(client, monkeypatch)
    item_id = items[0]["id"]
    await _review(client, item_id, "START_REVIEW")
    await _review(client, item_id, "APPROVE")

    plain = (await client.get(f"/api/workspaces/{ws_id}/evidence/export")).json()
    assert plain["include_history"] is False
    by_id = {entry["id"]: entry for entry in plain["items"]}
    assert by_id[item_id]["review_status"] == "APPROVED"
    assert all(entry["history"] is None for entry in plain["items"])

    rich = (
        await client.get(
            f"/api/workspaces/{ws_id}/evidence/export",
            params={"include_history": "true", "review_status": "APPROVED"},
        )
    ).json()
    assert rich["include_history"] is True
    assert [entry["id"] for entry in rich["items"]] == [item_id]
    assert [event["action"] for event in rich["items"][0]["history"]] == [
        "START_REVIEW",
        "APPROVE",
    ]

    markdown = (
        await client.get(
            f"/api/workspaces/{ws_id}/evidence/export.md", params={"include_history": "true"}
        )
    ).text
    assert "Review: APPROVED" in markdown
    assert "Review history:" in markdown
    assert "START_REVIEW" in markdown
