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

# job.stage values surfaced to the UI progress indicator
STAGE_QUEUED = "queued"
STAGE_EXTRACTING = "extracting"
STAGE_VECTORIZING = "vectorizing"
STAGE_READY = "ready"
STAGE_FAILED = "failed"


class PdfValidationError(Exception):
    """Deterministic input failure — retrying can never succeed."""


class UnexpectedProcessingError(Exception):
    """Transient/unknown failure; the queue executor decides whether to retry."""


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
    drafts_by_id = {draft.chunk_id(document.id): draft for draft in drafts}
    draft_ids = set(drafts_by_id)

    stale_ids = [chunk_id for chunk_id in existing_by_id if chunk_id not in draft_ids]
    await repo.delete_by_ids(stale_ids)

    # structural metadata is not part of the chunk id: refresh it in place on
    # surviving chunks so reprocessing doubles as the metadata backfill path
    for chunk_id, chunk in existing_by_id.items():
        draft = drafts_by_id.get(chunk_id)
        if draft is not None and (chunk.parent_clause_id, chunk.section_path) != (
            draft.parent_clause_id,
            draft.section_path,
        ):
            chunk.parent_clause_id = draft.parent_clause_id
            chunk.section_path = draft.section_path

    new_chunks = [
        Chunk(
            id=chunk_id,
            document_id=document.id,
            workspace_id=document.workspace_id,
            chunk_index=draft.chunk_index,
            page_start=draft.page_start,
            page_end=draft.page_end,
            clause_id=draft.clause_id,
            heading=draft.heading,
            parent_clause_id=draft.parent_clause_id,
            section_path=draft.section_path,
            text=draft.text,
            token_count=draft.token_count,
            content_hash=draft.content_hash,
        )
        for chunk_id, draft in drafts_by_id.items()
        if chunk_id not in existing_by_id
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


def _mark_failed(document: Document, job: ProcessingJob, message: str) -> None:
    document.status = DocumentStatus.FAILED
    job.status = JobStatus.FAILED
    job.stage = STAGE_FAILED
    job.error_message = message


async def mark_job_failed(job_id: uuid.UUID, message: str) -> None:
    """Terminal failure bookkeeping, used by the worker once retries are spent."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        job = await session.get(ProcessingJob, job_id)
        if job is None:
            logger.error("Cannot mark job %s failed: row missing", job_id)
            return
        document = await session.get(Document, job.document_id)
        job.status = JobStatus.FAILED
        job.stage = STAGE_FAILED
        job.error_message = message
        if document is not None:
            document.status = DocumentStatus.FAILED
        await session.commit()


async def process_document(
    document_id: uuid.UUID, job_id: uuid.UUID, *, fail_terminally: bool = True
) -> None:
    """Run the ingestion pipeline for one document with its own DB session.

    Executed in-process (BackgroundTasks fallback, CLI backfill) or by the arq
    worker. PdfValidationError is always terminal. For unexpected errors:
    fail_terminally=True marks the job FAILED here (no retry infrastructure);
    fail_terminally=False records the attempt and raises
    UnexpectedProcessingError so the queue's retry policy decides.

    Chunk writes are transactional and chunk ids deterministic, so a retried
    or re-run job overwrites cleanly — partial chunks never leak.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        job = await session.get(ProcessingJob, job_id)
        if document is None or job is None:
            logger.error("Processing skipped: document %s or job %s missing", document_id, job_id)
            return

        document.status = DocumentStatus.PROCESSING
        job.status = JobStatus.PROCESSING
        job.stage = STAGE_EXTRACTING
        job.attempts += 1
        await session.commit()

        try:
            sha256, page_texts = await anyio.to_thread.run_sync(
                _validate_and_extract, Path(document.storage_path), get_settings().max_pdf_pages
            )
            job.stage = STAGE_VECTORIZING
            await session.commit()
            await _index_chunks(session, document, page_texts)
        except PdfValidationError as exc:
            await session.rollback()  # discard any partially flushed chunks
            _mark_failed(document, job, str(exc))
        except Exception as exc:
            logger.exception("Unexpected error processing document %s", document_id)
            await session.rollback()
            if not fail_terminally:
                # stays PROCESSING for polling; the caller retries or fails it
                job.error_message = f"Attempt {job.attempts} failed: {exc}"
                await session.commit()
                raise UnexpectedProcessingError(str(exc)) from exc
            _mark_failed(document, job, f"Unexpected processing error: {exc}")
        else:
            document.sha256 = sha256
            document.page_count = len(page_texts)
            document.status = DocumentStatus.READY
            job.status = JobStatus.READY
            job.stage = STAGE_READY
        await session.commit()
