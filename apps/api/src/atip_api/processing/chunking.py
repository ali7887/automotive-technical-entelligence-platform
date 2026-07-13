"""Deterministic, clause-aware chunking of extracted PDF page text.

Pure functions only: the same page texts always produce the same chunks, hashes,
and (given a document id) the same chunk UUIDs, so re-processing is idempotent.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass

# Namespace for deterministic chunk ids; also used as stable Qdrant point ids.
CHUNK_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "atip:chunk")

# Clause numbering styles seen in automotive regulations:
#   UNECE / ISO style: "6.4.3.1 Some heading" (at least one dot, avoids bare list numbers)
#   FMVSS style:       "S5.1.2 Some heading" or "S4. Definitions"
_CLAUSE_LINE = re.compile(r"^(?P<clause>(?:S\d+(?:\.\d+)*|\d+(?:\.\d+)+))\.?\s+(?P<rest>\S.*)?$")

# Token targets from docs/07_DOC_PROCESSING.md (350-600 tokens). Tokens are
# estimated as chars/4, which is deterministic and close enough for sizing.
MIN_CHUNK_TOKENS = 200
SOFT_TARGET_TOKENS = 450
MAX_CHUNK_TOKENS = 600

_MAX_HEADING_LEN = 512
_MAX_SECTION_PATH_LEN = 1024


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    token_count: int
    page_start: int
    page_end: int
    clause_id: str | None
    heading: str | None
    parent_clause_id: str | None
    section_path: str | None
    content_hash: str

    def chunk_id(self, document_id: uuid.UUID) -> uuid.UUID:
        # id depends on text position/content only, NOT on structural metadata:
        # metadata refinements backfill in place without invalidating embeddings
        return uuid.uuid5(CHUNK_NAMESPACE, f"{document_id}:{self.chunk_index}:{self.content_hash}")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def detect_clause(line: str) -> tuple[str, str | None] | None:
    """Return (clause_id, heading) if the line starts a numbered clause, else None."""
    match = _CLAUSE_LINE.match(line.strip())
    if match is None:
        return None
    rest = match.group("rest")
    heading = rest.strip()[:_MAX_HEADING_LEN] if rest else None
    return match.group("clause"), heading


def clause_ancestors(clause_id: str) -> list[str]:
    """Dotted prefixes of a clause id, shortest first: S14.8.7 -> [S14, S14.8]."""
    parts = clause_id.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def clause_lineage(
    clause_id: str | None, headings_seen: dict[str, str | None]
) -> tuple[str | None, str | None]:
    """(parent_clause_id, section_path) from the clause headings seen so far.

    The parent is the nearest ancestor clause that actually appeared in the
    document (intermediate numbering levels are often never printed). The
    section path is the human-readable ancestry trail, e.g.
    "S14 Requirements > S14.8 Test conditions > S14.8.7 Dummy positioning".
    """
    if clause_id is None:
        return None, None
    seen = [ancestor for ancestor in clause_ancestors(clause_id) if ancestor in headings_seen]
    parent = seen[-1] if seen else None

    def label(cid: str) -> str:
        heading = headings_seen.get(cid)
        return f"{cid} {heading}" if heading else cid

    path = " > ".join([label(cid) for cid in [*seen, clause_id]])
    return parent, path[:_MAX_SECTION_PATH_LEN]


@dataclass
class _OpenChunk:
    lines: list[str]
    tokens: int
    page_start: int
    page_end: int
    clause_id: str | None
    heading: str | None


def chunk_pages(pages: list[str]) -> list[ChunkDraft]:
    """Chunk per-page extracted text into clause-aware retrieval units.

    Pages are 1-indexed. Chunks close at line boundaries when they reach the soft
    target, would exceed the max size, or when a new clause heading begins and the
    current chunk is large enough to stand alone.
    """
    drafts: list[ChunkDraft] = []
    current: _OpenChunk | None = None
    active_clause: str | None = None
    active_heading: str | None = None
    # clause id -> heading, in document order; ancestors precede descendants in
    # well-formed regulations, so lineage computed at flush time is complete
    headings_seen: dict[str, str | None] = {}

    def flush() -> None:
        nonlocal current
        if current is None or not current.lines:
            return
        text = "\n".join(current.lines)
        parent_clause_id, section_path = clause_lineage(current.clause_id, headings_seen)
        drafts.append(
            ChunkDraft(
                chunk_index=len(drafts),
                text=text,
                token_count=estimate_tokens(text),
                page_start=current.page_start,
                page_end=current.page_end,
                clause_id=current.clause_id,
                heading=current.heading,
                parent_clause_id=parent_clause_id,
                section_path=section_path,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
        current = None

    for page_number, page_text in enumerate(pages, start=1):
        for raw_line in page_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            line_tokens = estimate_tokens(line)
            clause = detect_clause(line)

            if clause is not None:
                if current is not None and current.tokens >= MIN_CHUNK_TOKENS:
                    flush()
                active_clause, active_heading = clause
                headings_seen.setdefault(active_clause, active_heading)

            if (
                current is not None
                and current.tokens + line_tokens > MAX_CHUNK_TOKENS
                and current.tokens >= MIN_CHUNK_TOKENS
            ):
                flush()

            if current is None:
                current = _OpenChunk(
                    lines=[],
                    tokens=0,
                    page_start=page_number,
                    page_end=page_number,
                    clause_id=active_clause,
                    heading=active_heading,
                )
            current.lines.append(line)
            current.tokens += line_tokens
            current.page_end = page_number

            if current.tokens >= SOFT_TARGET_TOKENS:
                flush()

    flush()
    return drafts
