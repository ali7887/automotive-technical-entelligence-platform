"""Optional reranking: HTTP client contract and graceful retrieval fallback."""

import json

import httpx
import pytest

from atip_api.ai.rerank import HttpRerankClient, get_rerank_client
from atip_api.config import Settings

from .pdf_utils import pdf_with_text

_FILLER = (
    "The vehicle manufacturer shall ensure that the requirements of this "
    "regulation are met for the whole life of the vehicle system. "
)

_PAGES = [
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


# --- HttpRerankClient unit tests (no network: httpx.MockTransport) ---


async def test_http_client_sends_standard_payload_and_parses_results():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.98},
                    {"index": 0, "relevance_score": 0.42},
                ]
            },
        )

    client = HttpRerankClient(
        url="http://rerank.internal/v1/rerank",
        model="rerank-lite",
        api_key="sk-test",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    hits = await client.rerank("wheel slip", ["chunk a", "chunk b"], top_n=2)

    assert seen["json"] == {
        "query": "wheel slip",
        "documents": ["chunk a", "chunk b"],
        "top_n": 2,
        "model": "rerank-lite",
    }
    assert seen["auth"] == "Bearer sk-test"
    assert hits == [(1, 0.98), (0, 0.42)]


async def test_http_client_drops_out_of_range_indices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [{"index": 7, "relevance_score": 0.9}, {"index": 0, "score": 0.5}]}
        )

    client = HttpRerankClient(
        url="http://rerank.internal/v1/rerank",
        model=None,
        api_key=None,
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    # index 7 does not exist -> dropped; "score" accepted as a fallback field
    assert await client.rerank("q", ["only one"], top_n=1) == [(0, 0.5)]


def test_get_rerank_client_is_gated_by_config():
    assert get_rerank_client(Settings(rerank_enabled=False)) is None
    assert get_rerank_client(Settings(rerank_enabled=True, rerank_url=None)) is None
    client = get_rerank_client(
        Settings(rerank_enabled=True, rerank_url="http://rerank.internal/v1/rerank")
    )
    assert isinstance(client, HttpRerankClient)


# --- retrieval integration: reorder on success, RRF fallback on failure ---


async def _workspace_with_document(client) -> str:
    response = await client.post("/api/workspaces", json={"name": "Rerank"})
    ws_id = response.json()["id"]
    upload = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("r13h.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    assert upload.status_code in (201, 202)
    return ws_id


class ReversingReranker:
    """Deterministic fake: scores candidates in reverse RRF order."""

    async def rerank(self, query, documents, top_n):
        indices = list(range(len(documents)))[::-1]
        return [(i, 1.0 - 0.01 * pos) for pos, i in enumerate(indices)][:top_n]


class ExplodingReranker:
    async def rerank(self, query, documents, top_n):
        raise RuntimeError("rerank endpoint down")


async def test_reranker_reorders_results(client, monkeypatch):
    ws_id = await _workspace_with_document(client)
    monkeypatch.setattr(
        "atip_api.ai.rerank.get_rerank_client", lambda settings: ReversingReranker()
    )

    plain = await client.post(f"/api/workspaces/{ws_id}/search", json={"query": "vehicle"})
    reranked_order = [r["chunk_id"] for r in plain.json()["results"]]
    assert plain.json()["rerank_used"] is True
    assert plain.json()["results"][0]["scores"]["rerank_rank"] == 1
    assert plain.json()["results"][0]["scores"]["rerank_score"] == pytest.approx(1.0)

    monkeypatch.setattr("atip_api.ai.rerank.get_rerank_client", lambda settings: None)
    rrf = await client.post(f"/api/workspaces/{ws_id}/search", json={"query": "vehicle"})
    rrf_order = [r["chunk_id"] for r in rrf.json()["results"]]
    assert rrf.json()["rerank_used"] is False
    assert rrf.json()["results"][0]["scores"]["rerank_rank"] is None

    assert len(rrf_order) > 1, "need at least two hits to observe reordering"
    assert reranked_order == rrf_order[::-1]


async def test_reranker_failure_falls_back_to_rrf(client, monkeypatch):
    ws_id = await _workspace_with_document(client)

    monkeypatch.setattr("atip_api.ai.rerank.get_rerank_client", lambda settings: None)
    baseline = await client.post(f"/api/workspaces/{ws_id}/search", json={"query": "vehicle"})

    monkeypatch.setattr(
        "atip_api.ai.rerank.get_rerank_client", lambda settings: ExplodingReranker()
    )
    degraded = await client.post(f"/api/workspaces/{ws_id}/search", json={"query": "vehicle"})

    assert degraded.status_code == 200
    assert degraded.json()["rerank_used"] is False
    assert [r["chunk_id"] for r in degraded.json()["results"]] == [
        r["chunk_id"] for r in baseline.json()["results"]
    ]
