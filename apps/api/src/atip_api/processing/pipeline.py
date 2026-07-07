import hashlib
import logging
import uuid
from pathlib import Path

import anyio.to_thread
from pypdf import PdfReader

from atip_api.db import get_session_factory
from atip_api.models import Document, DocumentStatus, JobStatus, ProcessingJob

logger = logging.getLogger(__name__)


class PdfValidationError(Exception):
    pass


def _validate_and_extract(path: Path) -> tuple[str, int]:
    """Phase 1 pipeline: validate PDF, confirm per-page text extraction works,
    return (sha256, page_count). Chunking/embedding is Phase 2."""
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise PdfValidationError("File is not a valid PDF (missing %PDF header)")
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        reader = PdfReader(path)
        page_count = len(reader.pages)
        for page in reader.pages:
            page.extract_text()
    except Exception as exc:
        raise PdfValidationError(f"Failed to parse PDF: {exc}") from exc
    if page_count == 0:
        raise PdfValidationError("PDF contains no pages")
    return sha256, page_count


async def process_document(document_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Background task: runs after the upload response with its own DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        job = await session.get(ProcessingJob, job_id)
        if document is None or job is None:
            logger.error("Processing skipped: document %s or job %s missing", document_id, job_id)
            return

        document.status = DocumentStatus.PROCESSING
        job.status = JobStatus.PROCESSING
        await session.commit()

        try:
            sha256, page_count = await anyio.to_thread.run_sync(
                _validate_and_extract, Path(document.storage_path)
            )
        except PdfValidationError as exc:
            document.status = DocumentStatus.FAILED
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
        except Exception as exc:
            logger.exception("Unexpected error processing document %s", document_id)
            document.status = DocumentStatus.FAILED
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected processing error: {exc}"
        else:
            document.sha256 = sha256
            document.page_count = page_count
            document.status = DocumentStatus.READY
            job.status = JobStatus.READY
        await session.commit()
