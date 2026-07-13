"""Parsing and verification of LLM output against retrieved chunks.

The model must emit an answer with inline [n] markers, then a `<<<CLAIMS>>>`
sentinel followed by a strict JSON claims block (see services/rag_prompts.py).
Everything here is deterministic and offline: claims are checked by matching
their quotes against the exact retrieved chunk text, so a citation can never
point at content that was not actually in front of the model.

Statuses (per prompts/03_verified_rag_strict.md):
- validated: the quote is found verbatim (modulo whitespace/case) in the chunk
- weak:      the source exists but the quote could not be verified
- failed:    the source index does not exist -> the citation is dropped
Zero validated citations -> not_found (the answer is withheld).
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

CitationStatus = Literal["validated", "weak"]
AnswerStatus = Literal["verified", "partial", "unsupported", "not_found"]

CLAIMS_SENTINEL = "<<<CLAIMS>>>"

NOT_FOUND_ANSWER = (
    "Not found. The retrieved sources do not contain verifiable support for an answer "
    "to this question."
)

# quotes shorter than this cannot meaningfully pin a claim to a source
_MIN_QUOTE_CHARS = 12
_SNIPPET_MAX_CHARS = 280

_MARKER_RE = re.compile(r"\[(\d{1,3})\]")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class RetrievedSource:
    """Provenance snapshot of one retrieved chunk, numbered as shown to the LLM."""

    index: int  # 1-based; matches inline [n] markers and claim source refs
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    clause_id: str | None
    page_start: int
    page_end: int
    text: str
    # clause ancestry trail shown to the LLM as structural context
    section_path: str | None = None


class ClaimCitation(BaseModel):
    source: int
    quote: str = ""


class Claim(BaseModel):
    text: str = ""
    citations: list[ClaimCitation] = Field(default_factory=list)


class ClaimsBlock(BaseModel):
    not_found: bool = False
    confidence: float | None = None
    claims: list[Claim] = Field(default_factory=list)


@dataclass(frozen=True)
class ParsedOutput:
    answer_md: str
    claims: ClaimsBlock | None  # None when the claims block is missing or malformed
    parse_error: str | None


@dataclass(frozen=True)
class VerifiedCitation:
    citation_id: int  # the inline [n] number
    source: RetrievedSource
    status: CitationStatus
    snippet: str  # verified quote, or a chunk excerpt when the quote failed to match


@dataclass(frozen=True)
class VerifiedAnswer:
    answer_md: str
    not_found: bool
    confidence: float | None
    status: AnswerStatus
    citations: list[VerifiedCitation]
    claims_total: int
    claims_validated: int
    citations_dropped: int
    warnings: list[str]


def parse_llm_output(raw: str) -> ParsedOutput:
    """Split the raw completion into answer text and the strict-JSON claims block."""
    answer, sep, tail = raw.partition(CLAIMS_SENTINEL)
    if not sep:
        return ParsedOutput(raw.strip(), None, "missing claims block")
    payload = tail.strip()
    # tolerate models wrapping the JSON in a code fence
    payload = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload)
    try:
        claims = ClaimsBlock.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError):
        return ParsedOutput(answer.strip(), None, "malformed claims JSON")
    if claims.confidence is not None:
        claims = claims.model_copy(update={"confidence": min(1.0, max(0.0, claims.confidence))})
    return ParsedOutput(answer.strip(), claims, None)


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).casefold().strip()


def quote_supported(quote: str, chunk_text: str) -> bool:
    normalized = _normalize(quote)
    return len(normalized) >= _MIN_QUOTE_CHARS and normalized in _normalize(chunk_text)


def _excerpt(text: str) -> str:
    flat = _WS_RE.sub(" ", text).strip()
    return flat if len(flat) <= _SNIPPET_MAX_CHARS else flat[: _SNIPPET_MAX_CHARS - 1] + "…"


def _strip_invalid_markers(answer_md: str, valid_indices: set[int]) -> str:
    """Remove inline [n] markers whose n is not a verifiable citation."""

    def replace(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(1)) in valid_indices else ""

    return _MARKER_RE.sub(replace, answer_md)


def verify_answer(parsed: ParsedOutput, sources: list[RetrievedSource]) -> VerifiedAnswer:
    """Check every claim citation against the retrieved chunk text.

    Provenance is sacred: only citations whose source index maps to a real
    retrieved chunk survive, and only quote-verified ones count as support.
    """
    by_index = {source.index: source for source in sources}
    warnings: list[str] = []

    if parsed.claims is None:
        reason = parsed.parse_error or "unknown parse error"
        warnings.append(f"Model output could not be verified ({reason}).")
        return VerifiedAnswer(
            answer_md=NOT_FOUND_ANSWER,
            not_found=True,
            confidence=None,
            status="unsupported",
            citations=[],
            claims_total=0,
            claims_validated=0,
            citations_dropped=0,
            warnings=warnings,
        )

    if parsed.claims.not_found:
        answer = _strip_invalid_markers(parsed.answer_md, set()) or NOT_FOUND_ANSWER
        return VerifiedAnswer(
            answer_md=answer,
            not_found=True,
            confidence=parsed.claims.confidence,
            status="not_found",
            citations=[],
            claims_total=len(parsed.claims.claims),
            claims_validated=0,
            citations_dropped=0,
            warnings=warnings,
        )

    dropped = 0
    any_weak = False
    claims_validated = 0
    # per source index, keep the best evidence seen across all claims
    best: dict[int, VerifiedCitation] = {}

    for claim in parsed.claims.claims:
        claim_validated = False
        for citation in claim.citations:
            source = by_index.get(citation.source)
            if source is None:
                dropped += 1
                warnings.append(f"Dropped citation to nonexistent source [{citation.source}].")
                continue
            if quote_supported(citation.quote, source.text):
                claim_validated = True
                # first validated quote wins; later claims must not displace it
                if source.index not in best or best[source.index].status != "validated":
                    snippet = _WS_RE.sub(" ", citation.quote).strip()
                    best[source.index] = VerifiedCitation(
                        source.index, source, "validated", snippet
                    )
            else:
                any_weak = True
                warnings.append(
                    f"Quote for source [{source.index}] was not found in the chunk text."
                )
                if source.index not in best:
                    best[source.index] = VerifiedCitation(
                        source.index, source, "weak", _excerpt(source.text)
                    )
        if claim_validated:
            claims_validated += 1

    # markers referenced in the answer but absent from claims: keep the source
    # visible as weak evidence rather than pretending it was verified
    for match in _MARKER_RE.finditer(parsed.answer_md):
        index = int(match.group(1))
        if index in by_index and index not in best:
            any_weak = True
            source = by_index[index]
            best[index] = VerifiedCitation(index, source, "weak", _excerpt(source.text))
        elif index not in by_index:
            dropped += 1
            warnings.append(f"Removed inline marker [{index}]: no such source was retrieved.")

    citations = [best[index] for index in sorted(best)]
    validated_count = sum(1 for citation in citations if citation.status == "validated")

    if validated_count == 0:
        # weak support -> not_found (prompts/03): never present an unverified answer
        return VerifiedAnswer(
            answer_md=NOT_FOUND_ANSWER,
            not_found=True,
            confidence=parsed.claims.confidence,
            status="unsupported",
            citations=citations,
            claims_total=len(parsed.claims.claims),
            claims_validated=0,
            citations_dropped=dropped,
            warnings=warnings,
        )

    status = "verified" if not any_weak and dropped == 0 else "partial"
    answer_md = _strip_invalid_markers(parsed.answer_md, set(best))
    return VerifiedAnswer(
        answer_md=answer_md,
        not_found=False,
        confidence=parsed.claims.confidence,
        status=status,
        citations=citations,
        claims_total=len(parsed.claims.claims),
        claims_validated=claims_validated,
        citations_dropped=dropped,
        warnings=warnings,
    )
