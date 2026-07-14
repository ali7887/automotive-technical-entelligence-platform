"""Integration tests for the Evidence Map endpoints.

A deterministic fake LLM proposes requirements citing whichever numbered source
in the extraction prompt contains its quote; verification then runs for real.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator

from .pdf_utils import pdf_with_text

_FILLER = (
    "The vehicle manufacturer shall ensure that the requirements of this "
    "regulation are met for the whole life of the vehicle system."
)

_PHOTO_QUOTE = "The luminous intensity shall not exceed 125 candela at test point H-V."
_PHOTO_REQUIREMENT = "Luminous intensity must not exceed 125 candela at test point H-V."

_PHOTO_PAGES = [
    "\n".join(["S5.1.2 Photometric requirements", _PHOTO_QUOTE, *[_FILLER] * 13]),
]


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


class ExtractionFakeLLM:
    """Proposes fixed requirements, citing the prompt source containing each quote."""

    def __init__(self, requirements: list[tuple[str, str]]) -> None:
        # (requirement_text, quote); quotes not found in any source cite source 1 as-is,
        # exercising the unverifiable-quote path
        self.requirements = requirements
        self.calls = 0

    def _raw(self, user: str) -> str:
        headers = list(re.finditer(r"^\[(\d+)\] Clause:", user, flags=re.MULTILINE))
        proposed = []
        for text, quote in self.requirements:
            index = 1
            for i, match in enumerate(headers):
                end = headers[i + 1].start() if i + 1 < len(headers) else len(user)
                if _normalize(quote) in _normalize(user[match.start() : end]):
                    index = int(match.group(1))
                    break
            proposed.append({"text": text, "citations": [{"source": index, "quote": quote}]})
        return json.dumps({"requirements": proposed})

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        self.calls += 1
        raw = self._raw(user)
        for start in range(0, len(raw), 7):
            yield raw[start : start + 7]


class MalformedFakeLLM:
    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        yield "I could not produce JSON, sorry."


def _install(monkeypatch, fake) -> None:
    monkeypatch.setattr("atip_api.ai.llm.get_llm_client", lambda settings: fake)


async def _create_workspace(client, name: str = "Homologation") -> str:
    response = await client.post("/api/workspaces", json={"name": name})
    return response.json()["id"]


async def _upload_ready(client, ws_id: str, pages: list[str], name: str) -> str:
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": (name, pdf_with_text(pages), "application/pdf")},
    )
    assert response.status_code == 202
    doc_id = response.json()["document"]["id"]
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"
    return doc_id


async def test_extract_persists_verified_requirement(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert response.status_code == 201
    payload = response.json()
    assert payload["requirements_seen"] == 1
    assert payload["requirements_dropped"] == 0
    assert payload["citations_dropped"] == 0
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert item["requirement_text"] == _PHOTO_REQUIREMENT
    assert item["document_name"] == "fmvss108.pdf"
    assert item["status"] == "OPEN"
    assert item["risk"] == "UNRATED"
    assert len(item["citations"]) == 1
    citation = item["citations"][0]
    assert _normalize(citation["quote"]) == _normalize(_PHOTO_QUOTE)
    assert citation["page_start"] == 1

    # the persisted citation maps to a real chunk of this document
    listed = (await client.get(f"/api/workspaces/{ws_id}/evidence")).json()
    assert [entry["id"] for entry in listed] == [item["id"]]


async def test_extract_drops_fabricated_quote(client, monkeypatch):
    _install(
        monkeypatch,
        ExtractionFakeLLM(
            [
                (_PHOTO_REQUIREMENT, _PHOTO_QUOTE),
                ("Fabricated limit of 999 candela.", "shall not exceed 999 candela"),
            ]
        ),
    )
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    payload = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    assert payload["requirements_seen"] == 2
    assert payload["requirements_dropped"] == 1
    assert payload["citations_dropped"] == 1
    assert [item["requirement_text"] for item in payload["items"]] == [_PHOTO_REQUIREMENT]
    assert any("unverifiable quote" in warning for warning in payload["warnings"])


async def test_extract_survives_malformed_llm_output(client, monkeypatch):
    _install(monkeypatch, MalformedFakeLLM())
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert response.status_code == 201
    payload = response.json()
    assert payload["items"] == []
    assert any("not valid JSON" in warning for warning in payload["warnings"])


async def test_reextract_replaces_previous_items(client, monkeypatch):
    fake = ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)])
    _install(monkeypatch, fake)
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    first = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    second = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()
    assert fake.calls == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]

    listed = (await client.get(f"/api/workspaces/{ws_id}/evidence")).json()
    assert [entry["id"] for entry in listed] == [second["items"][0]["id"]]


async def test_extract_without_api_key_returns_503(client):
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert response.status_code == 503
    assert response.json()["code"] == "generation_disabled"


async def test_extract_missing_document_returns_404(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([]))
    response = await client.post(f"/api/documents/{uuid.uuid4()}/evidence/extract")
    assert response.status_code == 404


async def test_extract_unprocessed_document_returns_409(client, monkeypatch):
    # corrupt uploads are rejected up front since Phase 6, so force a non-READY
    # status directly to exercise the extraction guard
    from atip_api.db import get_session_factory
    from atip_api.models import Document, DocumentStatus

    _install(monkeypatch, ExtractionFakeLLM([]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    async with get_session_factory()() as session:
        document = await session.get(Document, uuid.UUID(doc_id))
        assert document is not None
        document.status = DocumentStatus.PROCESSING
        await session.commit()

    response = await client.post(f"/api/documents/{doc_id}/evidence/extract")
    assert response.status_code == 409
    assert response.json()["code"] == "document_not_ready"


async def test_update_status_and_risk(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    item = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()["items"][0]

    response = await client.patch(
        f"/api/evidence/{item['id']}", json={"status": "COMPLIANT", "risk": "LOW"}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "COMPLIANT"
    assert updated["risk"] == "LOW"

    # partial update keeps the other field
    updated = (await client.patch(f"/api/evidence/{item['id']}", json={"risk": "HIGH"})).json()
    assert updated["status"] == "COMPLIANT"
    assert updated["risk"] == "HIGH"


async def test_update_missing_item_returns_404(client):
    response = await client.patch(f"/api/evidence/{uuid.uuid4()}", json={"status": "COMPLIANT"})
    assert response.status_code == 404


async def test_update_rejects_invalid_status(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    item = (await client.post(f"/api/documents/{doc_id}/evidence/extract")).json()["items"][0]

    response = await client.patch(f"/api/evidence/{item['id']}", json={"status": "MAYBE"})
    assert response.status_code == 422


async def test_list_filters_by_document(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client)
    doc_a = await _upload_ready(client, ws_id, _PHOTO_PAGES, "a.pdf")
    doc_b = await _upload_ready(client, ws_id, _PHOTO_PAGES, "b.pdf")
    await client.post(f"/api/documents/{doc_a}/evidence/extract")
    await client.post(f"/api/documents/{doc_b}/evidence/extract")

    all_items = (await client.get(f"/api/workspaces/{ws_id}/evidence")).json()
    assert len(all_items) == 2
    only_a = (
        await client.get(f"/api/workspaces/{ws_id}/evidence", params={"document_id": doc_a})
    ).json()
    assert len(only_a) == 1
    assert only_a[0]["document_id"] == doc_a


async def test_list_missing_workspace_returns_404(client):
    response = await client.get(f"/api/workspaces/{uuid.uuid4()}/evidence")
    assert response.status_code == 404


async def test_export_json_and_markdown(client, monkeypatch):
    _install(monkeypatch, ExtractionFakeLLM([(_PHOTO_REQUIREMENT, _PHOTO_QUOTE)]))
    ws_id = await _create_workspace(client, name="Homologation")
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    await client.post(f"/api/documents/{doc_id}/evidence/extract")

    exported = (await client.get(f"/api/workspaces/{ws_id}/evidence/export")).json()
    assert exported["workspace_name"] == "Homologation"
    assert len(exported["items"]) == 1
    assert exported["items"][0]["requirement_text"] == _PHOTO_REQUIREMENT

    response = await client.get(f"/api/workspaces/{ws_id}/evidence/export.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert _PHOTO_REQUIREMENT in response.text
    assert "S5.1.2" in response.text or "p. 1" in response.text
