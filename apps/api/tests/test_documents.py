import uuid

from atip_api.config import get_settings

from .pdf_utils import pdf_with_text


def _pdf_bytes(pages: int = 1) -> bytes:
    # real text layer: Phase 6 upload pre-checks reject text-less PDFs
    return pdf_with_text(["S5.1 General requirements for lighting devices."] * pages)


async def _create_workspace(client) -> str:
    response = await client.post("/api/workspaces", json={"name": "Regulations"})
    return response.json()["id"]


async def test_upload_and_process_pdf(client):
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("r155.pdf", _pdf_bytes(pages=3), "application/pdf")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["document"]["status"] == "PENDING"

    # ASGITransport awaits background tasks, so processing has finished by now
    document = (await client.get(f"/api/documents/{payload['document']['id']}")).json()
    assert document["status"] == "READY"
    assert document["page_count"] == 3
    assert document["sha256"] is not None and len(document["sha256"]) == 64

    job = (await client.get(f"/api/jobs/{payload['job']['id']}")).json()
    assert job["status"] == "READY"
    assert job["error_message"] is None


async def test_upload_corrupt_pdf_is_rejected_up_front(client):
    # Phase 6: corrupt files never become documents; the upload itself fails
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "pdf_corrupted"
    assert "not a valid PDF" in response.json()["detail"]


async def test_upload_rejects_non_pdf_extension(client):
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file_type"


async def test_upload_rejects_oversized_file(client):
    # conftest caps uploads at 1 MB
    ws_id = await _create_workspace(client)
    response = await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("big.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024), "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


async def test_upload_to_missing_workspace_returns_404(client):
    response = await client.post(
        f"/api/workspaces/{uuid.uuid4()}/documents",
        files={"file": ("r155.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 404


async def test_get_document_file_streams_pdf(client):
    ws_id = await _create_workspace(client)
    upload = (
        await client.post(
            f"/api/workspaces/{ws_id}/documents",
            files={"file": ("r155.pdf", _pdf_bytes(pages=2), "application/pdf")},
        )
    ).json()

    response = await client.get(f"/api/documents/{upload['document']['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "inline" in response.headers["content-disposition"]
    assert "r155.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")


async def test_get_document_file_missing_document_returns_404(client):
    response = await client.get(f"/api/documents/{uuid.uuid4()}/file")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_get_document_file_missing_stored_file_returns_404(client):
    ws_id = await _create_workspace(client)
    upload = (
        await client.post(
            f"/api/workspaces/{ws_id}/documents",
            files={"file": ("r155.pdf", _pdf_bytes(), "application/pdf")},
        )
    ).json()
    doc_id = upload["document"]["id"]

    # uploads are stored as {document_id}.pdf under the configured storage dir
    (get_settings().storage_dir / f"{doc_id}.pdf").unlink()

    response = await client.get(f"/api/documents/{doc_id}/file")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_list_documents(client):
    ws_id = await _create_workspace(client)
    assert (await client.get(f"/api/workspaces/{ws_id}/documents")).json() == []
    await client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("r155.pdf", _pdf_bytes(), "application/pdf")},
    )
    documents = (await client.get(f"/api/workspaces/{ws_id}/documents")).json()
    assert len(documents) == 1
    assert documents[0]["name"] == "r155.pdf"
