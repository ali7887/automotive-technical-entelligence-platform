"""Upload-time PDF validation: corrupt, encrypted, oversized, scanned (Phase 6)."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from atip_api.config import get_settings

from .pdf_utils import pdf_with_text

_PAGE = "S5.1 General requirements\nEach headlamp shall conform to Table XIX."


async def _create_workspace(client) -> str:
    response = await client.post("/api/workspaces", json={"name": "Hardening"})
    return response.json()["id"]


async def _upload(client, ws_id: str, name: str, data: bytes):
    return await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": (name, data, "application/pdf")},
    )


def _encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.append(BytesIO(pdf_with_text([_PAGE])))
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _storage_files() -> list[Path]:
    storage = get_settings().storage_dir
    return list(storage.glob("*.pdf")) if storage.exists() else []


async def test_upload_without_pdf_signature_is_rejected(client):
    ws_id = await _create_workspace(client)
    before = len(_storage_files())
    response = await _upload(client, ws_id, "fake.pdf", b"MZ this is not a pdf at all")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "pdf_corrupted"
    assert body["type"] == "/errors/pdf_corrupted"
    # no document row and no orphaned file
    assert (await client.get(f"/api/workspaces/{ws_id}/documents")).json() == []
    assert len(_storage_files()) == before


async def test_upload_truncated_pdf_is_rejected(client):
    ws_id = await _create_workspace(client)
    response = await _upload(client, ws_id, "broken.pdf", b"%PDF-1.4\ngarbage without xref")
    assert response.status_code == 422
    assert response.json()["code"] == "pdf_corrupted"


async def test_upload_encrypted_pdf_is_rejected(client):
    ws_id = await _create_workspace(client)
    response = await _upload(client, ws_id, "locked.pdf", _encrypted_pdf())
    assert response.status_code == 422
    assert response.json()["code"] == "pdf_encrypted"
    assert (await client.get(f"/api/workspaces/{ws_id}/documents")).json() == []


async def test_upload_beyond_page_limit_is_rejected(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_pages", 3)
    ws_id = await _create_workspace(client)
    response = await _upload(client, ws_id, "big.pdf", pdf_with_text([_PAGE] * 4))
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"
    assert "pages" in response.json()["detail"]


async def test_valid_pdf_still_uploads_and_processes(client):
    ws_id = await _create_workspace(client)
    response = await _upload(client, ws_id, "ok.pdf", pdf_with_text([_PAGE]))
    assert response.status_code == 201
    doc_id = response.json()["document"]["id"]
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "READY"


def test_encrypted_fixture_really_is_encrypted():
    reader = PdfReader(BytesIO(_encrypted_pdf()))
    assert reader.is_encrypted
