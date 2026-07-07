import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy import select

from atip_api.db import get_session_factory
from atip_api.models import Chunk
from atip_api.services.retrieval import reciprocal_rank_fusion

from .pdf_utils import pdf_with_text

_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
_C = uuid.UUID("00000000-0000-0000-0000-00000000000c")


def test_rrf_scores_are_explicit():
    scores = reciprocal_rank_fusion([[_A, _B], [_B, _C]], k=60)
    assert scores[_A] == pytest.approx(1 / 61)
    assert scores[_B] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[_C] == pytest.approx(1 / 62)
    # a chunk found by both legs outranks single-leg chunks at similar ranks
    assert scores[_B] > scores[_A] > scores[_C]


def test_rrf_empty_rankings():
    assert reciprocal_rank_fusion([], k=60) == {}
    assert reciprocal_rank_fusion([[], []], k=60) == {}


def test_rrf_single_leg_preserves_order():
    scores = reciprocal_rank_fusion([[_A, _B, _C]], k=60)
    assert sorted(scores, key=lambda cid: -scores[cid]) == [_A, _B, _C]


_FILLER = (
    "The vehicle manufacturer shall ensure that the requirements of this "
    "regulation are met for the whole life of the vehicle system. "
)

_BRAKE_PAGES = [
    "\n".join(["5.2.1 Braking system requirements", *[_FILLER.strip()] * 14]),
    "\n".join(
        [
            "5.2.2 Anti-lock braking performance",
            "The antilock braking system shall control wheel slip on surfaces with a "
            "low coefficient of adhesion without driver intervention.",
            *[_FILLER.strip()] * 13,
        ]
    ),
]

_LAMP_PAGES = [
    "\n".join(
        [
            "S5.1.2 Photometric requirements",
            "Each headlamp shall meet the photometric luminous intensity values "
            "specified in Table XIX for the applicable beam pattern.",
            *[_FILLER.strip()] * 13,
        ]
    ),
]


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


async def test_keyword_search_returns_provenance(client):
    ws_id = await _create_workspace(client)
    doc_id = await _upload_ready(client, ws_id, _LAMP_PAGES, "fmvss108.pdf")

    response = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "photometric luminous intensity"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == ws_id
    assert body["semantic_used"] is False  # no embedding key configured in tests
    assert body["results"], "expected at least one keyword hit"

    top = body["results"][0]
    assert top["document_id"] == doc_id
    assert top["document_name"] == "fmvss108.pdf"
    assert top["workspace_id"] == ws_id
    assert top["version_id"] is None
    assert top["clause_id"] == "S5.1.2"
    assert top["heading"] == "Photometric requirements"
    assert top["page_start"] == 1
    assert "photometric" in top["text"].lower()
    assert top["scores"]["keyword_rank"] == 1
    assert top["scores"]["keyword_score"] > 0
    assert top["scores"]["semantic_rank"] is None
    assert top["scores"]["rrf"] == pytest.approx(1 / 61)


async def test_search_is_scoped_to_workspace(client):
    ws_a = await _create_workspace(client, "A")
    ws_b = await _create_workspace(client, "B")
    await _upload_ready(client, ws_a, _LAMP_PAGES, "fmvss108.pdf")

    response = await client.post(
        f"/api/workspaces/{ws_b}/search", json={"query": "photometric luminous intensity"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_document_filter(client):
    ws_id = await _create_workspace(client)
    brake_doc = await _upload_ready(client, ws_id, _BRAKE_PAGES, "r13h.pdf")
    lamp_doc = await _upload_ready(client, ws_id, _LAMP_PAGES, "fmvss108.pdf")

    unfiltered = await client.post(f"/api/workspaces/{ws_id}/search", json={"query": "vehicle"})
    found_docs = {result["document_id"] for result in unfiltered.json()["results"]}
    assert found_docs == {brake_doc, lamp_doc}

    filtered = await client.post(
        f"/api/workspaces/{ws_id}/search",
        json={"query": "vehicle", "document_id": brake_doc},
    )
    assert filtered.status_code == 200
    results = filtered.json()["results"]
    assert results and all(result["document_id"] == brake_doc for result in results)


async def test_search_no_match_returns_empty(client):
    ws_id = await _create_workspace(client)
    await _upload_ready(client, ws_id, _BRAKE_PAGES, "r13h.pdf")
    response = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "zylonite quasar"}
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_missing_workspace_returns_404(client):
    response = await client.post(f"/api/workspaces/{uuid.uuid4()}/search", json={"query": "brakes"})
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_search_rejects_blank_query(client):
    ws_id = await _create_workspace(client)
    for payload in ({"query": ""}, {"query": "   "}, {}):
        response = await client.post(f"/api/workspaces/{ws_id}/search", json=payload)
        assert response.status_code == 422


async def test_search_rejects_bad_top_k(client):
    ws_id = await _create_workspace(client)
    for top_k in (0, 51, -1):
        response = await client.post(
            f"/api/workspaces/{ws_id}/search", json={"query": "brakes", "top_k": top_k}
        )
        assert response.status_code == 422


class FakeEmbeddingClient:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]


async def test_hybrid_search_fuses_semantic_and_keyword(client, monkeypatch):
    ws_id = await _create_workspace(client)
    brake_doc = await _upload_ready(client, ws_id, _BRAKE_PAGES, "r13h.pdf")
    await _upload_ready(client, ws_id, _LAMP_PAGES, "fmvss108.pdf")

    # keyword leg will rank the ABS chunk first for this query; the fake semantic
    # leg returns the *other* brake chunk so fusion must merge both
    async with get_session_factory()() as session:
        chunks = list(
            (
                await session.scalars(
                    select(Chunk).where(Chunk.document_id == uuid.UUID(brake_doc))
                )
            ).all()
        )
    abs_chunk = next(chunk for chunk in chunks if "antilock" in chunk.text)
    other_chunk = next(chunk for chunk in chunks if chunk.id != abs_chunk.id)

    async def fake_semantic(settings, vector, workspace_id, document_id, limit):
        return [(other_chunk.id, 0.91), (abs_chunk.id, 0.87)]

    monkeypatch.setattr(
        "atip_api.ai.embeddings.get_embedding_client", lambda s: FakeEmbeddingClient()
    )
    monkeypatch.setattr("atip_api.vectorstore.search_chunk_vectors", fake_semantic)

    response = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "antilock wheel slip", "top_k": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["semantic_used"] is True

    by_id = {result["chunk_id"]: result for result in body["results"]}
    abs_result = by_id[str(abs_chunk.id)]
    other_result = by_id[str(other_chunk.id)]

    # found by both legs -> keyword rank 1 + semantic rank 2 beats semantic-only rank 1
    assert abs_result["scores"]["keyword_rank"] == 1
    assert abs_result["scores"]["semantic_rank"] == 2
    assert abs_result["scores"]["semantic_score"] == pytest.approx(0.87)
    assert abs_result["scores"]["rrf"] == pytest.approx(1 / 61 + 1 / 62)
    assert other_result["scores"]["keyword_rank"] is None
    assert other_result["scores"]["semantic_rank"] == 1
    assert other_result["scores"]["rrf"] == pytest.approx(1 / 61)
    assert abs_result["scores"]["rrf"] > other_result["scores"]["rrf"]
    assert body["results"][0]["chunk_id"] == str(abs_chunk.id)
