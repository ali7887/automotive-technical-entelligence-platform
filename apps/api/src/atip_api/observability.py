"""Correlation IDs and structured JSON logging.

The correlation id is taken from an incoming `X-Request-ID` header (or
generated), stored in a contextvar for the duration of the request, echoed in
the response header, and stamped on every log record and problem-details body.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from atip_api.config import Settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

_REQUEST_ID_HEADER = b"x-request-id"
# incoming ids are untrusted; cap length and keep them header-safe
_MAX_INCOMING_ID_LEN = 64


def get_request_id() -> str | None:
    return _request_id.get()


class CorrelationIdMiddleware:
    """Pure ASGI middleware (BaseHTTPMiddleware buffers SSE streams; this doesn't)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(_REQUEST_ID_HEADER, b"").decode("latin-1").strip()
        request_id = (
            incoming[:_MAX_INCOMING_ID_LEN]
            if incoming and incoming.isprintable()
            else uuid.uuid4().hex
        )
        token = _request_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((_REQUEST_ID_HEADER, request_id.encode("latin-1")))
            await send(message)

        try:
            await self._app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line; tracebacks are a single string field."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id is not None:
            entry["request_id"] = request_id
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


_configured = False


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once per process; later calls are no-ops so
    repeated app factories (tests) don't stack handlers or evict pytest's."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stderr)
    if settings.log_json:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root.handlers = [handler]
