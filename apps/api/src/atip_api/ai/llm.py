"""OpenAI-compatible chat-completion client abstraction.

Mirrors ai/embeddings.py: a small streaming protocol so the RAG service can be
tested with a deterministic fake, and `None` when no API key is configured.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from openai import AsyncOpenAI

from atip_api.config import Settings


class LLMClient(Protocol):
    def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        """Yield answer text deltas for a single-turn chat completion."""
        ...


class OpenAIChatClient:
    def __init__(self, api_key: str, model: str, base_url: str | None) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        # temperature 0: verified extraction must be as deterministic as the API allows
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        async for event in response:
            if event.choices and (delta := event.choices[0].delta.content):
                yield delta


def get_llm_client(settings: Settings) -> LLMClient | None:
    """Return the configured chat client, or None when no API key is set."""
    if not settings.openai_api_key:
        return None
    return OpenAIChatClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model,
        base_url=settings.openai_base_url,
    )
