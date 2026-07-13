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
    # set only when the optional reranker scored this chunk
    rerank_rank: int | None = None
    rerank_score: float | None = None


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
    # clause ancestry trail, e.g. "S14 Requirements > S14.8 … > S14.8.7 …"
    section_path: str | None = None
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
    # False when reranking is disabled or the reranker failed (RRF order used)
    rerank_used: bool = False
    results: list[SearchResult]
