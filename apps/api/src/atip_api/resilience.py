"""Retry policies for transient downstream failures (Phase 6).

Exponential backoff with full jitter via tenacity. Only errors that are
plausibly transient are retried; anything else propagates immediately.
Streaming LLM responses are only retried while establishing the stream —
a stream that dies mid-flight must fail, not silently restart.
"""

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from sqlalchemy.exc import InterfaceError, OperationalError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

TRANSIENT_OPENAI_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)

TRANSIENT_DB_ERRORS = (OperationalError, InterfaceError, ConnectionError, OSError)

_MAX_ATTEMPTS = 3


def openai_retrying() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception_type(TRANSIENT_OPENAI_ERRORS),
        wait=wait_random_exponential(multiplier=0.5, max=8),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        reraise=True,
    )


def db_retrying() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception_type(TRANSIENT_DB_ERRORS),
        wait=wait_random_exponential(multiplier=0.2, max=2),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        reraise=True,
    )
