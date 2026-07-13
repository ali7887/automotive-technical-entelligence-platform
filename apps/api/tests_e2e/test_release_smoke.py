"""Release-critical flows over real HTTP; doubles as the post-deploy checklist.

Covered: health probes, RFC 7807 problem shape + request-id propagation,
upload -> READY -> keyword search with provenance, corrupt/encrypted PDF
rejection, and the /ask contract with or without an LLM configured.
"""

import asyncio
import io
import time
import uuid

import httpx
from pypdf import PdfReader, PdfWriter
from tests.pdf_utils import pdf_with_text

_PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id"}
_READY_TIMEOUT_SECONDS = 90.0


async def _upload(
    client: httpx.AsyncClient, workspace_id: str, name: str, content: bytes
) -> httpx.Response:
    return await client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": (name, content, "application/pdf")},
    )


def _assert_problem(response: httpx.Response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) >= _PROBLEM_KEYS, body
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == f"/errors/{code}"
    return body


async def test_health_endpoints_report_full_stack(client: httpx.AsyncClient):
    live = await client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert live.json()["version"]

    ready = await client.get("/health/ready")
    assert ready.status_code == 200, ready.text
    # post-deploy target state: fully ready, not merely degraded
    assert ready.json()["status"] == "ready", ready.text

    health = await client.get("/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["status"] == "ok"
    assert {"postgres", "redis", "qdrant"} == set(body["services"])


async def test_problem_details_and_request_id_propagation(client: httpx.AsyncClient):
    request_id = f"e2e-smoke-{uuid.uuid4().hex[:8]}"
    response = await client.get(
        f"/api/workspaces/{uuid.uuid4()}", headers={"X-Request-ID": request_id}
    )
    body = _assert_problem(response, 404, "not_found")
    assert body["request_id"] == request_id
    assert response.headers["x-request-id"] == request_id


async def test_validation_errors_are_sanitized_problems(client: httpx.AsyncClient):
    response = await client.get("/api/workspaces/not-a-uuid")
    body = _assert_problem(response, 422, "validation_error")
    for item in body["errors"]:
        assert set(item) == {"loc", "msg"}  # pydantic internals must not leak


async def test_upload_to_ready_to_keyword_search(client: httpx.AsyncClient, workspace: dict):
    token = f"zqxbrake{uuid.uuid4().hex[:10]}"
    pdf = pdf_with_text(
        [
            f"5.1 Parking brake\nThe parking brake {token} shall hold the vehicle "
            "on a 20 percent grade.",
            "5.2 Service brake\nThe service brake shall decelerate the vehicle.",
        ]
    )
    upload = await _upload(client, workspace["id"], "e2e-regulation.pdf", pdf)
    assert upload.status_code == 201, upload.text
    document = upload.json()["document"]

    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while True:
        current = (await client.get(f"/api/documents/{document['id']}")).json()
        if current["status"] == "READY":
            break
        assert current["status"] != "FAILED", f"processing failed: {current}"
        assert time.monotonic() < deadline, f"document not READY in time: {current}"
        await asyncio.sleep(0.5)
    assert current["page_count"] == 2

    search = await client.post(
        f"/api/workspaces/{workspace['id']}/search", json={"query": token}
    )
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert results, "keyword search must find the uploaded clause"
    top = results[0]
    assert top["document_id"] == document["id"]
    assert token in top["text"]
    assert top["page_start"] == 1  # provenance survives the pipeline

    listed = (await client.get(f"/api/workspaces/{workspace['id']}/documents")).json()
    assert [doc["status"] for doc in listed if doc["id"] == document["id"]] == ["READY"]


async def test_corrupt_pdf_rejected_cleanly(client: httpx.AsyncClient, workspace: dict):
    response = await _upload(
        client, workspace["id"], "broken.pdf", b"%PDF-1.4 not really a pdf"
    )
    _assert_problem(response, 422, "pdf_corrupted")
    listed = (await client.get(f"/api/workspaces/{workspace['id']}/documents")).json()
    assert listed == []  # rejected uploads must not create document rows


async def test_encrypted_pdf_rejected_cleanly(client: httpx.AsyncClient, workspace: dict):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf_with_text(["secret clause text"]))))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    response = await _upload(client, workspace["id"], "locked.pdf", buffer.getvalue())
    _assert_problem(response, 422, "pdf_encrypted")


async def test_ask_contract_with_or_without_llm(client: httpx.AsyncClient, workspace: dict):
    """/ask must either answer (LLM configured) or degrade to a clean 503
    problem — never a raw 500. Which branch runs depends on the deployment."""
    response = await client.post(
        f"/api/workspaces/{workspace['id']}/ask", json={"question": "What holds the vehicle?"}
    )
    if response.status_code == 503:
        _assert_problem(response, 503, "generation_disabled")
    else:
        assert response.status_code == 200, response.text
        body = response.json()
        assert "answer" in body
        assert "citations" in body
