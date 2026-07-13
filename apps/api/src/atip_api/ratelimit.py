"""Sliding-window rate limiting for resource-heavy endpoints.

Memory-backed and per-process: state lives on `app.state.rate_limiter`, keyed
by bucket + client IP. The limiter is a plain interface — a Redis-backed
implementation can replace it behind the same `check` signature when the API
runs multi-process. Exceeding a limit raises RateLimitedError (429 problem
details with a Retry-After header).
"""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, Request

from atip_api.config import Settings, get_settings
from atip_api.errors import RateLimitedError

_WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: float = _WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, now: float | None = None) -> int | None:
        """Record a hit and return None, or the Retry-After seconds when over limit.

        No awaits inside: safe without a lock on a single event loop.
        """
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if not hits:
            del self._hits[key]  # keep the key space bounded
            hits = self._hits[key]
        if len(hits) >= limit:
            return max(1, math.ceil(self._window - (now - hits[0])))
        hits.append(now)
        return None


def rate_limited(bucket: str, get_limit: Callable[[Settings], int]):
    """Router dependency enforcing a per-client per-minute limit for `bucket`."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
        client = request.client.host if request.client else "unknown"
        retry_after = limiter.check(f"{bucket}:{client}", get_limit(settings))
        if retry_after is not None:
            raise RateLimitedError(
                f"Too many {bucket} requests. Retry in {retry_after} seconds.",
                retry_after=retry_after,
            )

    return Depends(dependency)
