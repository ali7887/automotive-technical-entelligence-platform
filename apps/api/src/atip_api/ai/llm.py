"""OpenAI-compatible chat-completion client abstraction.

Mirrors ai/embeddings.py: a small streaming protocol so the RAG service can be
tested with a deterministic fake, and `None` when no API key is configured.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from openai import AsyncOpenAI

from atip_api.config import Settings
from atip_api.resilience import openai_retrying


class LLMClient(Protocol):
    def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        """Yield answer text deltas for a single-turn chat completion."""
        ...


class OpenAIChatClient:
    def __init__(
        self, api_key: str, model: str, base_url: str | None, timeout: float
    ) -> None:
        # SDK retries disabled: tenacity owns the retry policy
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0
        )
        self._model = model

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        # transient failures are retried only while establishing the stream;
        # a stream dying mid-flight propagates (a restart could emit duplicates)
        response = None
        async for attempt in openai_retrying():
            with attempt:
                # temperature 0: verified extraction must be as deterministic
                # as the API allows
                response = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    stream=True,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
        assert response is not None
        async for event in response:
            if event.choices and (delta := event.choices[0].delta.content):
                yield delta


def get_llm_client(settings: Settings) -> LLMClient | None:
    """Return the configured chat client, or None when no API key is set."""
    api_key = settings.openai_api_key_value
    if api_key is None:
        return None
    return OpenAIChatClient(
        api_key=api_key,
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout_seconds,
    )
