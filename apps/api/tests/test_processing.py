import uuid
from collections.abc import Sequence
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy import select

from atip_api import vectorstore
from atip_api.db import get_session_factory
from atip_api.models import Chunk
from atip_api.processing.pipeline import process_document

from .pdf_utils import pdf_with_text

_BODY = (
    "Each headlamp shall be designed to conform to the photometric requirements "
    "of Table XIX when tested according to the procedure of this section. "
)

_PAGES = [
    "\n".join(["S5.1 General requirements", *[_BODY.strip()] * 14]),
    "\n".join(["S5.1.2 Photometric requirements", *[_BODY.strip()] * 14]),
]


async def _create_workspace(client) -> str:
    response = await client.post("/api/workspaces", json={"name": "Regulations"})
    return response.json()["id"]


async def _upload(client, ws_id: str, pages: list[str]) -> dict:
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("fmvss108.pdf", pdf_with_text(pages), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


async def _get_chunks(document_id: str) -> list[Chunk]:
    async with get_session_factory()() as session:
        result = await session.scalars(
            select(Chunk)
            .where(Chunk.document_id == uuid.UUID(document_id))
            .order_by(Chunk.chunk_index)
        )
        return list(result.all())


async def test_upload_persists_chunks_with_provenance(client):
    ws_id = await _create_workspace(client)
    payload = await _upload(client, ws_id, _PAGES)
    doc_id = payload["document"]["id"]

    document = (await client.get(f"/api/documents/{doc_id}")).json()
    assert document["status"] == "READY"

    chunks = await _get_chunks(doc_id)
    assert len(chunks) >= 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert str(chunk.workspace_id) == ws_id
        assert 1 <= chunk.page_start <= chunk.page_end <= 2
        assert chunk.text
        assert chunk.token_count > 0
        assert len(chunk.content_hash) == 64
        assert chunk.embedded_at is None  # no embedding key configured in tests
    assert chunks[0].clause_id == "S5.1"
    assert any(chunk.clause_id == "S5.1.2" for chunk in chunks)


async def test_reprocessing_unchanged_document_keeps_chunk_ids(client):
    ws_id = await _create_workspace(client)
    payload = await _upload(client, ws_id, _PAGES)
    doc_id, job_id = payload["document"]["id"], payload["job"]["id"]

    before = [(chunk.id, chunk.content_hash) for chunk in await _get_chunks(doc_id)]
    await process_document(uuid.UUID(doc_id), uuid.UUID(job_id))
    after = [(chunk.id, chunk.content_hash) for chunk in await _get_chunks(doc_id)]

    assert before == after
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text) % 7)] * 4 for text in texts]


async def test_embedding_and_qdrant_upsert(client, monkeypatch):
    fake_client = FakeEmbeddingClient()
    upserts: list[list[tuple[Chunk, list[float]]]] = []

    async def fake_upsert(settings, items):
        upserts.append(list(items))

    monkeypatch.setattr("atip_api.ai.embeddings.get_embedding_client", lambda s: fake_client)
    monkeypatch.setattr("atip_api.vectorstore.upsert_chunk_vectors", fake_upsert)

    ws_id = await _create_workspace(client)
    payload = await _upload(client, ws_id, _PAGES)
    doc_id, job_id = payload["document"]["id"], payload["job"]["id"]

    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"
    chunks = await _get_chunks(doc_id)
    assert all(chunk.embedded_at is not None for chunk in chunks)

    assert len(upserts) == 1
    upserted = upserts[0]
    assert {chunk.id for chunk, _ in upserted} == {chunk.id for chunk in chunks}
    for chunk, vector in upserted:
        assert len(vector) == 4
        chunk_payload = vectorstore.chunk_payload(chunk)
        assert chunk_payload["postgres_chunk_id"] == str(chunk.id)
        assert chunk_payload["workspace_id"] == ws_id
        assert chunk_payload["document_id"] == doc_id
        assert chunk_payload["version_id"] is None
        assert chunk_payload["chunk_text"] == chunk.text
        assert chunk_payload["page_start"] == chunk.page_start

    # re-processing unchanged content must not re-embed already-embedded chunks
    await process_document(uuid.UUID(doc_id), uuid.UUID(job_id))
    assert len(upserts) == 1
    assert len(fake_client.calls) == 1


async def test_blank_pdf_yields_ready_document_without_chunks(client):
    # scanned/blank PDFs have no text layer; OCR is out of scope, doc stays READY
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)

    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("blank.pdf", buffer.getvalue(), "application/pdf")},
    )
    doc_id = response.json()["document"]["id"]
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"
    assert await _get_chunks(doc_id) == []
