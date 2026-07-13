"""Optional cross-encoder reranking of fused retrieval candidates.

Speaks the de-facto standard rerank HTTP API (Cohere / Jina / HuggingFace TEI
compatible): POST {model?, query, documents[], top_n} returns
{"results": [{"index": <candidate index>, "relevance_score": <float>}, ...]}.

A local cross-encoder was rejected deliberately: it would pull torch into the
production image for marginal gain at this corpus size. Reranking is disabled
by default and retrieval falls back to plain RRF ordering whenever the
reranker is disabled, misconfigured, or fails at runtime — never an exception
to the caller.
"""

import logging
from typing import Any, Protocol

import httpx

from atip_api.config import Settings

logger = logging.getLogger(__name__)


class RerankClient(Protocol):
    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        """Return (candidate_index, relevance_score) pairs, most relevant first."""
        ...


class HttpRerankClient:
    def __init__(
        self,
        url: str,
        model: str | None,
        api_key: str | None,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport  # injection point for tests

    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        payload: dict[str, Any] = {"query": query, "documents": documents, "top_n": top_n}
        if self._model:
            payload["model"] = self._model
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()

        results: list[tuple[int, float]] = []
        for item in body.get("results", []):
            index = int(item["index"])
            score = float(item.get("relevance_score", item.get("score", 0.0)))
            # an out-of-range index would corrupt provenance; drop it loudly
            if 0 <= index < len(documents):
                results.append((index, score))
            else:
                logger.warning("Reranker returned out-of-range index %d; ignored", index)
        return results


def get_rerank_client(settings: Settings) -> RerankClient | None:
    """Return the configured rerank client, or None when reranking is off."""
    if not settings.rerank_enabled:
        return None
    if not settings.rerank_url:
        logger.warning("RERANK_ENABLED is set but RERANK_URL is empty; reranking skipped")
        return None
    return HttpRerankClient(
        url=settings.rerank_url,
        model=settings.rerank_model,
        api_key=settings.rerank_api_key_value,
        timeout=settings.rerank_timeout_seconds,
    )
