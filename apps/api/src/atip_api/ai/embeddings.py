"""OpenAI-compatible embedding client abstraction.

Isolated behind a small protocol so the pipeline and retrieval service can be
tested with a deterministic fake, and so a batch can be retried independently.
"""

import logging
from collections.abc import Sequence
from typing import Protocol

from openai import AsyncOpenAI

from atip_api.config import Settings
from atip_api.resilience import openai_retrying

logger = logging.getLogger(__name__)

_BATCH_SIZE = 128


class EmbeddingClient(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingClient:
    def __init__(
        self, api_key: str, model: str, dimensions: int, base_url: str | None, timeout: float
    ) -> None:
        # SDK retries disabled: tenacity owns the retry policy
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0
        )
        self._model = model
        self._dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = list(texts[start : start + _BATCH_SIZE])
            response = None
            async for attempt in openai_retrying():
                with attempt:
                    response = await self._client.embeddings.create(
                        model=self._model, input=batch, dimensions=self._dimensions
                    )
            assert response is not None
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        return vectors


def get_embedding_client(settings: Settings) -> EmbeddingClient | None:
    """Return the configured embedding client, or None when no API key is set."""
    if not settings.openai_api_key:
        return None
    return OpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout_seconds,
    )
