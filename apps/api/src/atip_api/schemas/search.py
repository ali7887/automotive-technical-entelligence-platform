import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    document_id: uuid.UUID | None = None
    top_k: int = Field(default=10, ge=1, le=50)


class SearchScores(BaseModel):
    """Rank/score breakdown per retrieval leg plus the fused RRF score."""

    rrf: float
    keyword_rank: int | None = None
    keyword_score: float | None = None
    semantic_rank: int | None = None
    semantic_score: float | None = None


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    version_id: uuid.UUID | None = None
    document_name: str
    chunk_index: int
    page_start: int
    page_end: int
    clause_id: str | None
    heading: str | None
    text: str
    scores: SearchScores


class SearchResponse(BaseModel):
    query: str
    workspace_id: uuid.UUID
    document_id: uuid.UUID | None
    top_k: int
    # False when embeddings are not configured or the semantic leg failed;
    # results are then keyword-only
    semantic_used: bool
    results: list[SearchResult]
