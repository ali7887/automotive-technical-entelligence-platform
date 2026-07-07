"""Integration tests for the verified RAG endpoints (POST /ask, GET /chat SSE).

A deterministic fake LLM is injected in place of the OpenAI client; the fake
streams its raw completion in small pieces so sentinel holdback is exercised.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import select

from atip_api.db import get_session_factory
from atip_api.models import Chunk
from atip_api.services.verification import CLAIMS_SENTINEL, NOT_FOUND_ANSWER

from .pdf_utils import pdf_with_text

_FILLER = (
    "The vehicle manufacturer shall ensure that the requirements of this "
    "regulation are met for the whole life of the vehicle system."
)

_PHOTO_QUOTE = "The luminous intensity shall not exceed 125 candela at test point H-V."

_PHOTO_PAGES = [
    "\n".join(["S5.1.2 Photometric requirements", _PHOTO_QUOTE, *[_FILLER] * 13]),
]

_BRAKE_PAGES = [
    "\n".join(
        [
            "5.2.2 Anti-lock braking performance",
            "The antilock braking system shall control wheel slip on surfaces with a "
            "low coefficient of adhesion without driver intervention.",
            *[_FILLER] * 13,
        ]
    ),
]

# FTS ANDs all non-stopword terms, so the question sticks to words present in the chunk
_QUESTION = "What is the luminous intensity at test point H-V?"


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


class FakeLLM:
    """Streams a fixed raw completion in small pieces."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        self.calls += 1
        for start in range(0, len(self.raw), 7):
            yield self.raw[start : start + 7]


class CitingFakeLLM:
    """Cites whichever numbered source in the prompt contains `quote`."""

    def __init__(self, quote: str, answer: str = "The maximum is 125 candela") -> None:
        self.quote = quote
        self.answer = answer
        self.calls = 0

    def _raw(self, user: str) -> str:
        headers = list(re.finditer(r"^\[(\d+)\] Document:", user, flags=re.MULTILINE))
        index = None
        for i, match in enumerate(headers):
            end = headers[i + 1].start() if i + 1 < len(headers) else len(user)
            if _normalize(self.quote) in _normalize(user[match.start() : end]):
                index = int(match.group(1))
                break
        assert index is not None, "quote not found in any prompt source"
        claims = {
            "not_found": False,
            "confidence": 0.9,
            "claims": [
                {"text": self.answer, "citations": [{"source": index, "quote": self.quote}]}
            ],
        }
        return f"{self.answer} [{index}]\n{CLAIMS_SENTINEL}\n{json.dumps(claims)}"

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        self.calls += 1
        raw = self._raw(user)
        for start in range(0, len(raw), 7):
            yield raw[start : start + 7]


def _install(monkeypatch, fake) -> None:
    monkeypatch.setattr("atip_api.ai.llm.get_llm_client", lambda settings: fake)


def _claims_raw(answer: str, claims_json: str) -> str:
    return f"{answer}\n{CLAIMS_SENTINEL}\n{claims_json}"


async def _create_workspace(client, name: str = "Regulations") -> str:
    response = await client.post("/api/workspaces", json={"name": name})
    return response.json()["id"]


async def _upload_ready(client, ws_id: str, pages: list[str], name: str) -> str:
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": (name, pdf_with_text(pages), "application/pdf")},
    )
    assert response.status_code == 201
    doc_id = response.json()["document"]["id"]
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"
    return doc_id


async def _chunk_ids(document_id: str) -> set[str]:
    async with get_session_factory()() as session:
        result = await session.scalars(
            select(Chunk.id).where(Chunk.document_id == uuid.UUID(document_id))
        )
        return {str(chunk_id) for chunk_id in result.all()}


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


# --- graceful degradation without an API key ---


async def test_ask_without_key_returns_generation_disabled(client):
    ws_id = await _create_workspace(client)
    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "generation_disabled"
    assert "OPENAI_API_KEY" in body["message"]


async def test_chat_without_key_streams_error_event(client):
    ws_id = await _create_workspace(client)
    response = await client.get(
        f"/api/workspaces/{ws_id}/chat", params={"question": _QUESTION}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "generation_disabled"


# --- verified answers ---


async def test_ask_returns_verified_citations_mapping_to_real_chunks(client, monkeypatch):
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    fake = CitingFakeLLM(_PHOTO_QUOTE)
    _install(monkeypatch, fake)

    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    assert response.status_code == 200
    body = response.json()

    assert body["not_found"] is False
    assert body["verification"]["status"] == "verified"
    assert body["verification"]["claims_validated"] == 1
    assert body["confidence"] == 0.9
    assert body["sources"], "expected retrieved sources"
    assert fake.calls == 1

    assert len(body["citations"]) == 1
    citation = body["citations"][0]
    assert citation["status"] == "validated"
    assert citation["postgres_chunk_id"] in await _chunk_ids(doc_id)
    assert citation["clause_id"] == "S5.1.2"
    assert citation["page_start"] == 1
    assert citation["source_text_snippet"] == _PHOTO_QUOTE
    # the inline marker in the answer matches the structured citation
    assert f"[{citation['citation_id']}]" in body["answer_md"]


async def test_ask_with_fabricated_quote_is_not_found(client, monkeypatch):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    fake = FakeLLM(
        _claims_raw(
            "The maximum is 500 candela [1]",
            json.dumps(
                {
                    "not_found": False,
                    "confidence": 0.9,
                    "claims": [
                        {
                            "text": "max 500 candela",
                            "citations": [
                                {"source": 1, "quote": "shall not exceed 500 candela"}
                            ],
                        }
                    ],
                }
            ),
        )
    )
    _install(monkeypatch, fake)

    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    body = response.json()
    assert body["not_found"] is True
    assert body["verification"]["status"] == "unsupported"
    assert body["answer_md"] == NOT_FOUND_ANSWER
    assert all(citation["status"] == "weak" for citation in body["citations"])


async def test_ask_with_fake_source_index_drops_citation(client, monkeypatch):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    fake = FakeLLM(
        _claims_raw(
            "See [99]",
            json.dumps(
                {
                    "not_found": False,
                    "confidence": 0.9,
                    "claims": [
                        {"text": "x", "citations": [{"source": 99, "quote": _PHOTO_QUOTE}]}
                    ],
                }
            ),
        )
    )
    _install(monkeypatch, fake)

    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    body = response.json()
    assert body["not_found"] is True
    assert body["citations"] == []
    assert body["verification"]["citations_dropped"] >= 1
    assert "[99]" not in body["answer_md"]


async def test_ask_with_malformed_claims_is_not_found(client, monkeypatch):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    _install(monkeypatch, FakeLLM(_claims_raw("Hallucinated answer [1]", "{broken json")))

    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    body = response.json()
    assert body["not_found"] is True
    assert body["answer_md"] == NOT_FOUND_ANSWER
    assert body["citations"] == []
    assert any("could not be verified" in warning for warning in body["verification"]["warnings"])


async def test_ask_unanswerable_question_is_not_found(client, monkeypatch):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    _install(
        monkeypatch,
        FakeLLM(
            _claims_raw(
                "The retrieved sources do not cover seat belt anchorages.",
                json.dumps({"not_found": True, "confidence": 0.2, "claims": []}),
            )
        ),
    )

    response = await client.post(
        f"/api/workspaces/{ws_id}/ask", json={"question": "Seat belt anchorage requirements?"}
    )
    body = response.json()
    assert body["not_found"] is True
    assert body["verification"]["status"] == "not_found"
    assert body["citations"] == []


async def test_ask_empty_workspace_short_circuits_llm(client, monkeypatch):
    ws_id = await _create_workspace(client)
    fake = CitingFakeLLM(_PHOTO_QUOTE)
    _install(monkeypatch, fake)

    response = await client.post(f"/api/workspaces/{ws_id}/ask", json={"question": _QUESTION})
    body = response.json()
    assert response.status_code == 200
    assert body["not_found"] is True
    assert body["sources"] == []
    assert fake.calls == 0, "LLM must not be called when nothing was retrieved"


async def test_ask_missing_workspace_returns_404(client, monkeypatch):
    _install(monkeypatch, CitingFakeLLM(_PHOTO_QUOTE))
    response = await client.post(
        f"/api/workspaces/{uuid.uuid4()}/ask", json={"question": _QUESTION}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_ask_rejects_blank_question(client):
    ws_id = await _create_workspace(client)
    for payload in ({"question": ""}, {"question": "   "}, {}):
        response = await client.post(f"/api/workspaces/{ws_id}/ask", json=payload)
        assert response.status_code == 422


# --- SSE chat ---


async def test_chat_streams_sources_tokens_then_verified_final(client, monkeypatch):
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    _install(monkeypatch, CitingFakeLLM(_PHOTO_QUOTE))

    response = await client.get(f"/api/workspaces/{ws_id}/chat", params={"question": _QUESTION})
    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]

    assert names[0] == "sources"
    assert names[-1] == "final"
    assert "token" in names
    assert "error" not in names

    sources = events[0][1]["sources"]
    assert sources and all(source["document_id"] == doc_id for source in sources)

    draft = "".join(payload["text"] for name, payload in events if name == "token")
    assert CLAIMS_SENTINEL not in draft, "claims block must never leak into tokens"
    assert "The maximum is 125 candela" in draft

    final = events[-1][1]
    assert final["not_found"] is False
    assert final["verification"]["status"] == "verified"
    assert final["citations"][0]["source_text_snippet"] == _PHOTO_QUOTE


async def test_chat_scopes_sources_to_document(client, monkeypatch):
    ws_id = await _create_workspace(client)
    brake_doc = await _upload_ready(client, ws_id, _BRAKE_PAGES, "r13h.pdf")
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")
    _install(
        monkeypatch,
        FakeLLM(_claims_raw("No answer.", json.dumps({"not_found": True, "claims": []}))),
    )

    response = await client.get(
        f"/api/workspaces/{ws_id}/chat",
        params={"question": "vehicle requirements", "document_id": brake_doc},
    )
    events = _parse_sse(response.text)
    sources = events[0][1]["sources"]
    assert sources and all(source["document_id"] == brake_doc for source in sources)


async def test_chat_missing_workspace_streams_error(client, monkeypatch):
    _install(monkeypatch, CitingFakeLLM(_PHOTO_QUOTE))
    response = await client.get(
        f"/api/workspaces/{uuid.uuid4()}/chat", params={"question": _QUESTION}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "not_found"


async def test_chat_llm_failure_streams_error(client, monkeypatch):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _PHOTO_PAGES, "fmvss108.pdf")

    class ExplodingLLM:
        async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
            raise RuntimeError("boom")
            yield ""  # pragma: no cover

    _install(monkeypatch, ExplodingLLM())
    response = await client.get(f"/api/workspaces/{ws_id}/chat", params={"question": _QUESTION})
    events = _parse_sse(response.text)
    assert events[0][0] == "sources"
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "generation_failed"
