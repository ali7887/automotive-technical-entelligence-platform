import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio.to_thread
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api import vectorstore
from atip_api.ai import embeddings
from atip_api.config import get_settings
from atip_api.db import get_session_factory
from atip_api.models import Chunk, Document, DocumentStatus, JobStatus, ProcessingJob
from atip_api.processing.chunking import chunk_pages
from atip_api.repositories.chunks import ChunkRepository

logger = logging.getLogger(__name__)


class PdfValidationError(Exception):
    pass


def _validate_and_extract(path: Path, max_pages: int) -> tuple[str, list[str]]:
    """Validate the PDF and extract per-page text. Returns (sha256, page_texts).

    Uploads are pre-checked (pdf_checks.precheck_pdf), but the pipeline
    re-validates fully: it sees every page, and stored files may predate the
    pre-check or be reprocessed.
    """
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise PdfValidationError("File is not a valid PDF (missing %PDF header)")
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise PdfValidationError(
                "PDF_ENCRYPTED: password-protected PDFs are not supported"
            )
        if len(reader.pages) > max_pages:
            raise PdfValidationError(
                f"PDF_TOO_MANY_PAGES: {len(reader.pages)} pages exceeds the {max_pages} limit"
            )
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except PdfValidationError:
        raise
    except Exception as exc:
        raise PdfValidationError(f"Failed to parse PDF: {exc}") from exc
    if not page_texts:
        raise PdfValidationError("PDF contains no pages")
    if not any(text.strip() for text in page_texts):
        raise PdfValidationError(
            "EMPTY_TEXT_LAYER: no extractable text (scanned PDFs are not supported)"
        )
    return sha256, page_texts


async def _index_chunks(session: AsyncSession, document: Document, pages: list[str]) -> None:
    """Chunk extracted text, persist to Postgres, and embed/upsert vectors to Qdrant.

    Chunk ids are deterministic (document + index + content hash), so unchanged
    chunks keep their id and embedding; only new content is embedded and stale
    chunks/vectors are removed.
    """
    settings = get_settings()
    repo = ChunkRepository(session)

    drafts = chunk_pages(pages)
    existing = await repo.list_by_document(document.id)
    existing_by_id = {chunk.id: chunk for chunk in existing}
    draft_ids = {draft.chunk_id(document.id) for draft in drafts}

    stale_ids = [chunk_id for chunk_id in existing_by_id if chunk_id not in draft_ids]
    await repo.delete_by_ids(stale_ids)

    new_chunks = [
        Chunk(
            id=draft.chunk_id(document.id),
            document_id=document.id,
            workspace_id=document.workspace_id,
            chunk_index=draft.chunk_index,
            page_start=draft.page_start,
            page_end=draft.page_end,
            clause_id=draft.clause_id,
            heading=draft.heading,
            text=draft.text,
            token_count=draft.token_count,
            content_hash=draft.content_hash,
        )
        for draft in drafts
        if draft.chunk_id(document.id) not in existing_by_id
    ]
    await repo.add_all(new_chunks)

    if stale_ids:
        try:
            await vectorstore.delete_chunk_vectors(settings, stale_ids)
        except Exception:
            logger.warning(
                "Could not delete %d stale vectors for document %s",
                len(stale_ids),
                document.id,
                exc_info=True,
            )

    to_embed = new_chunks + [
        chunk for chunk in existing if chunk.id in draft_ids and chunk.embedded_at is None
    ]
    if not to_embed:
        return
    client = embeddings.get_embedding_client(settings)
    if client is None:
        logger.warning(
            "OPENAI_API_KEY not set: %d chunks of document %s stored without embeddings; "
            "search will be keyword-only until embeddings are configured",
            len(to_embed),
            document.id,
        )
        return
    try:
        vectors = await client.embed([chunk.text for chunk in to_embed])
        await vectorstore.upsert_chunk_vectors(settings, list(zip(to_embed, vectors, strict=True)))
        await repo.mark_embedded([chunk.id for chunk in to_embed], datetime.now(UTC))
    except Exception:
        # embedding/Qdrant outage must not fail ingestion: chunks are stored,
        # keyword search works, and unembedded chunks are picked up on reprocess
        logger.warning(
            "Embedding failed for %d chunks of document %s; document stays searchable "
            "keyword-only until reprocessed",
            len(to_embed),
            document.id,
            exc_info=True,
        )


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
            sha256, page_texts = await anyio.to_thread.run_sync(
                _validate_and_extract, Path(document.storage_path), get_settings().max_pdf_pages
            )
            await _index_chunks(session, document, page_texts)
        except PdfValidationError as exc:
            await session.rollback()  # discard any partially flushed chunks
            document.status = DocumentStatus.FAILED
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
        except Exception as exc:
            logger.exception("Unexpected error processing document %s", document_id)
            await session.rollback()
            document.status = DocumentStatus.FAILED
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected processing error: {exc}"
        else:
            document.sha256 = sha256
            document.page_count = len(page_texts)
            document.status = DocumentStatus.READY
            job.status = JobStatus.READY
        await session.commit()
