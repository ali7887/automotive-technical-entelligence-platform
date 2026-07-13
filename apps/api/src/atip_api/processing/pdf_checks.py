"""Structural PDF validation run at upload time, before a document is accepted.

Synchronous and blocking (pypdf): callers on the event loop must go through
anyio.to_thread. The full-document text check stays in the processing
pipeline; this pre-check only samples a few pages so uploads stay fast.
"""

from pathlib import Path

from pypdf import PdfReader

from atip_api.errors import (
    AppError,
    EmptyTextLayerError,
    FileTooLargeError,
    PdfCorruptedError,
    PdfEncryptedError,
)

PDF_MAGIC = b"%PDF-"
_SCAN_SAMPLE_PAGES = 5


def _sample_indexes(page_count: int) -> list[int]:
    """First/last plus evenly spread interior pages — cheap scan detection."""
    if page_count <= _SCAN_SAMPLE_PAGES:
        return list(range(page_count))
    step = (page_count - 1) / (_SCAN_SAMPLE_PAGES - 1)
    return sorted({round(i * step) for i in range(_SCAN_SAMPLE_PAGES)})


def precheck_pdf(path: Path, max_pages: int) -> None:
    """Raise a typed AppError for corrupt, encrypted, oversized, or scanned PDFs."""
    with path.open("rb") as fh:
        if fh.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise PdfCorruptedError("File is not a valid PDF (missing %PDF header)")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise PdfEncryptedError(
                "The PDF is password-protected; encrypted PDFs are not supported"
            )
        page_count = len(reader.pages)
        if page_count == 0:
            raise PdfCorruptedError("PDF contains no pages")
        if page_count > max_pages:
            raise FileTooLargeError(f"PDF has {page_count} pages; the limit is {max_pages}")
        if not any(
            (reader.pages[i].extract_text() or "").strip() for i in _sample_indexes(page_count)
        ):
            raise EmptyTextLayerError(
                "The PDF has no extractable text layer (likely a scan). "
                "OCR is not supported; upload a text-based PDF."
            )
    except AppError:
        raise
    except Exception as exc:
        raise PdfCorruptedError(f"Failed to parse PDF: {exc}") from exc
