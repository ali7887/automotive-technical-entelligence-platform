"""RFC 7807 problem details, correlation ids, and structured logging."""

import json
import logging
import sys
import uuid

from httpx import ASGITransport, AsyncClient

from atip_api.main import create_app
from atip_api.observability import JsonLogFormatter, _request_id

_PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id"}


def _assert_problem_shape(response, *, status: int, code: str) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body.keys() >= _PROBLEM_KEYS
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == f"/errors/{code}"
    assert body["title"]
    assert body["detail"]
    return body


async def test_app_error_is_rfc7807(client):
    missing = uuid.uuid4()
    response = await client.get(f"/api/workspaces/{missing}")
    body = _assert_problem_shape(response, status=404, code="not_found")
    assert body["instance"] == f"/api/workspaces/{missing}"


async def test_validation_error_is_rfc7807_with_safe_errors(client):
    response = await client.get("/api/workspaces/not-a-uuid")
    body = _assert_problem_shape(response, status=422, code="validation_error")
    assert isinstance(body["errors"], list) and body["errors"]
    entry = body["errors"][0]
    assert set(entry.keys()) == {"loc", "msg"}


async def test_unknown_route_is_rfc7807(client):
    response = await client.get("/api/definitely-not-a-route")
    _assert_problem_shape(response, status=404, code="http_error")


async def test_request_id_is_generated_and_echoed(client):
    response = await client.get(f"/api/workspaces/{uuid.uuid4()}")
    request_id = response.headers["x-request-id"]
    assert request_id
    assert response.json()["request_id"] == request_id


async def test_incoming_request_id_is_propagated(client):
    response = await client.get(
        f"/api/workspaces/{uuid.uuid4()}", headers={"X-Request-ID": "corr-abc-123"}
    )
    assert response.headers["x-request-id"] == "corr-abc-123"
    assert response.json()["request_id"] == "corr-abc-123"


async def test_unhandled_exception_is_masked(caplog):
    app = create_app()

    @app.get("/api/_test/boom")
    async def boom():  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("secret internal detail: db password is hunter2")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        with caplog.at_level(logging.ERROR):
            response = await test_client.get("/api/_test/boom")

    body = _assert_problem_shape(response, status=500, code="internal_error")
    # internals are logged, never returned
    assert "hunter2" not in json.dumps(body)
    assert "RuntimeError" not in json.dumps(body)
    assert any("Unhandled error" in record.message for record in caplog.records)


def test_json_log_formatter_shape():
    formatter = JsonLogFormatter()
    token = _request_id.set("corr-log-1")
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="atip_api.test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="something %s",
                args=("failed",),
                exc_info=sys.exc_info(),
            )
        entry = json.loads(formatter.format(record))
    finally:
        _request_id.reset(token)
    assert entry["level"] == "ERROR"
    assert entry["logger"] == "atip_api.test"
    assert entry["message"] == "something failed"
    assert entry["request_id"] == "corr-log-1"
    assert "ValueError: boom" in entry["exc_info"]
    assert entry["timestamp"].endswith("+00:00")
