import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class AskRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    document_id: uuid.UUID | None = None
    top_k: int = Field(default=8, ge=1, le=20)


class RetrievedSourceRead(BaseModel):
    """A retrieved chunk as numbered in the prompt; streamed before generation."""

    index: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    clause_id: str | None
    page_start: int
    page_end: int


CitationStatus = Literal["validated", "weak"]


class Citation(BaseModel):
    """A verified citation; `citation_id` matches inline [n] markers in the answer."""

    citation_id: int
    postgres_chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    clause_id: str | None
    page_start: int
    page_end: int
    # exact quote verified against the chunk text; a chunk excerpt when status is "weak"
    source_text_snippet: str
    status: CitationStatus


AnswerStatus = Literal["verified", "partial", "unsupported", "not_found"]


class AnswerVerification(BaseModel):
    status: AnswerStatus
    claims_total: int
    claims_validated: int
    citations_dropped: int
    warnings: list[str]


class AskResponse(BaseModel):
    question: str
    workspace_id: uuid.UUID
    document_id: uuid.UUID | None
    answer_md: str
    not_found: bool
    confidence: float | None
    citations: list[Citation]
    verification: AnswerVerification
    sources: list[RetrievedSourceRead]
    # False when embeddings are unavailable; retrieval was then keyword-only
    semantic_used: bool
    model: str


# --- SSE stream payloads (GET /api/workspaces/{id}/chat) ---


class SourcesEvent(BaseModel):
    sources: list[RetrievedSourceRead]


class TokenEvent(BaseModel):
    text: str


class StreamErrorEvent(BaseModel):
    code: str
    message: str
