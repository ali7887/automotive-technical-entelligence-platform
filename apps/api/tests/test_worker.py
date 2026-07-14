"""Async ingestion: enqueue/fallback wiring, worker retry states, stale jobs.

The worker task is exercised directly against the test DB (no Redis broker
needed): arq's contribution at runtime is delivery and the `Retry` signal,
both of which are simulated here with a fake ctx.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from arq.worker import Retry
from sqlalchemy import update

from atip_api import queue
from atip_api.config import Settings, get_settings
from atip_api.db import get_session_factory
from atip_api.models import Document, JobStatus, ProcessingJob
from atip_api.observability import get_request_id
from atip_api.processing.pipeline import STAGE_FAILED, STAGE_QUEUED, STAGE_READY
from atip_api.worker import process_document_task

from .pdf_utils import pdf_with_text

_PAGES = ["S5.1 General requirements\nEach headlamp shall conform to Table XIX."]


async def _create_workspace(client) -> str:
    response = await client.post("/api/workspaces", json={"name": "Async"})
    return response.json()["id"]


async def _upload_pending(client, monkeypatch) -> tuple[str, str]:
    """Upload with the queue 'accepting' the job so nothing runs inline."""

    async def fake_enqueue(settings, document_id, job_id, request_id):
        return True

    monkeypatch.setattr("atip_api.routers.documents.enqueue_process_document", fake_enqueue)
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["document"]["status"] == "PENDING"
    assert payload["job"]["status"] == "PENDING"
    assert payload["job"]["stage"] == STAGE_QUEUED
    return payload["document"]["id"], payload["job"]["id"]


async def _job(job_id: str) -> ProcessingJob:
    async with get_session_factory()() as session:
        job = await session.get(ProcessingJob, uuid.UUID(job_id))
        assert job is not None
        return job


async def _document(document_id: str) -> Document:
    async with get_session_factory()() as session:
        document = await session.get(Document, uuid.UUID(document_id))
        assert document is not None
        return document


# --- enqueue wiring ---


async def test_upload_returns_202_and_queued_job(client, monkeypatch):
    _doc_id, job_id = await _upload_pending(client, monkeypatch)
    job = await _job(job_id)
    assert job.attempts == 0
    assert job.request_id, "the upload's correlation id must be recorded on the job"


async def test_enqueue_disabled_returns_false_without_redis():
    settings = Settings(queue_enabled=False)
    assert (
        await queue.enqueue_process_document(settings, uuid.uuid4(), uuid.uuid4(), "req") is False
    )


async def test_enqueue_failure_reports_fallback(monkeypatch):
    async def broken_pool(settings):
        raise ConnectionError("redis down")

    monkeypatch.setattr("atip_api.queue.get_pool", broken_pool)
    settings = Settings(queue_enabled=True)
    assert (
        await queue.enqueue_process_document(settings, uuid.uuid4(), uuid.uuid4(), "req") is False
    )


async def test_enqueue_failure_falls_back_to_inline_processing(client, monkeypatch):
    async def fake_enqueue(settings, document_id, job_id, request_id):
        return False

    monkeypatch.setattr("atip_api.routers.documents.enqueue_process_document", fake_enqueue)
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("reg.pdf", pdf_with_text(_PAGES), "application/pdf")},
    )
    assert response.status_code == 202
    doc_id = response.json()["document"]["id"]
    # ASGITransport awaits background tasks: the inline fallback has finished
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"


# --- worker execution & retry states ---


async def test_worker_processes_document_to_ready(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)

    await process_document_task({"job_try": 1}, doc_id, job_id, "req-worker-1")

    job = await _job(job_id)
    assert job.status == JobStatus.READY
    assert job.stage == STAGE_READY
    assert job.attempts == 1
    assert (await _document(doc_id)).status.value == "READY"


async def test_worker_transient_failure_raises_retry_then_recovers(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)

    calls = {"n": 0}
    real_index = None
    from atip_api.processing import pipeline as pipeline_module

    real_index = pipeline_module._index_chunks

    async def flaky_index(session, document, pages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient db hiccup")
        await real_index(session, document, pages)

    monkeypatch.setattr("atip_api.processing.pipeline._index_chunks", flaky_index)

    with pytest.raises(Retry):
        await process_document_task({"job_try": 1}, doc_id, job_id, "req-retry")

    job = await _job(job_id)
    assert job.status == JobStatus.PROCESSING, "retryable failure must stay in flight"
    assert job.attempts == 1
    assert "Attempt 1 failed" in (job.error_message or "")

    await process_document_task({"job_try": 2}, doc_id, job_id, "req-retry")
    job = await _job(job_id)
    assert job.status == JobStatus.READY
    assert job.attempts == 2


async def test_worker_exhausted_retries_mark_job_failed(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)

    async def always_broken(session, document, pages):
        raise ConnectionError("permanently down")

    monkeypatch.setattr("atip_api.processing.pipeline._index_chunks", always_broken)

    last_try = get_settings().job_max_tries
    # the final allowed try must NOT raise Retry: it settles the job instead
    await process_document_task({"job_try": last_try}, doc_id, job_id, "req-exhaust")

    job = await _job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.stage == STAGE_FAILED
    assert f"after {last_try} attempts" in (job.error_message or "")
    assert (await _document(doc_id)).status.value == "FAILED"


async def test_worker_pdf_validation_error_is_terminal_on_first_try(client, monkeypatch, tmp_path):
    doc_id, job_id = await _upload_pending(client, monkeypatch)
    # corrupt the stored file after upload: deterministic input failure
    from pathlib import Path

    Path((await _document(doc_id)).storage_path).write_bytes(b"not a pdf at all")

    # must not raise Retry: retrying a corrupt file can never succeed
    await process_document_task({"job_try": 1}, doc_id, job_id, "req-corrupt")
    job = await _job(job_id)
    assert job.status == JobStatus.FAILED
    assert "not a valid PDF" in (job.error_message or "")


async def test_worker_restores_request_id_for_correlation(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)

    seen: dict = {}

    async def spying_index(session, document, pages):
        seen["request_id"] = get_request_id()

    monkeypatch.setattr("atip_api.processing.pipeline._index_chunks", spying_index)
    await process_document_task({"job_try": 1}, doc_id, job_id, "req-correlate-42")
    assert seen["request_id"] == "req-correlate-42"
    assert get_request_id() is None, "contextvar must be reset after the task"


# --- gated search: unfinished documents are invisible to retrieval ---


async def test_pending_document_is_not_searchable_until_ready(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)
    ws_id = str((await _document(doc_id)).workspace_id)

    before = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "headlamp Table XIX"}
    )
    assert before.status_code == 200
    assert before.json()["results"] == [], "PENDING document must not be searchable"

    await process_document_task({"job_try": 1}, doc_id, job_id, "req-gate")
    after = await client.post(
        f"/api/workspaces/{ws_id}/search", json={"query": "headlamp Table XIX"}
    )
    assert [r["document_id"] for r in after.json()["results"]] == [doc_id]


# --- crash safety: no job hangs forever ---


async def test_stale_processing_job_is_failed_on_read(client, monkeypatch):
    doc_id, job_id = await _upload_pending(client, monkeypatch)

    stale = datetime.now(UTC) - timedelta(seconds=get_settings().job_stale_after_seconds + 60)
    async with get_session_factory()() as session:
        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == uuid.UUID(job_id))
            .values(status=JobStatus.PROCESSING, updated_at=stale)
        )
        await session.commit()

    response = await client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert "did not finish" in body["error_message"]
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "FAILED"


async def test_fresh_processing_job_is_not_touched(client, monkeypatch):
    _, job_id = await _upload_pending(client, monkeypatch)
    response = await client.get(f"/api/jobs/{job_id}")
    assert response.json()["status"] == "PENDING"
