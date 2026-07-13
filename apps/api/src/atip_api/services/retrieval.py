import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from atip_api import vectorstore
from atip_api.ai import embeddings
from atip_api.config import Settings
from atip_api.errors import NotFoundError
from atip_api.repositories.chunks import ChunkRepository
from atip_api.repositories.workspaces import WorkspaceRepository
from atip_api.schemas.search import SearchRequest, SearchResponse, SearchResult, SearchScores

logger = logging.getLogger(__name__)

# candidates fetched per retrieval leg before fusion
_MIN_LEG_LIMIT = 20
_MAX_LEG_LIMIT = 50


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]], k: int
) -> dict[uuid.UUID, float]:
    """RRF: score(d) = sum over rankings of 1 / (k + rank(d)), ranks starting at 1."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return dict(scores)


class SearchService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._settings = settings
        self._chunks = ChunkRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def search(self, workspace_id: uuid.UUID, request: SearchRequest) -> SearchResponse:
        if await self._workspaces.get(workspace_id) is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        leg_limit = min(_MAX_LEG_LIMIT, max(_MIN_LEG_LIMIT, request.top_k * 3))

        keyword_hits = await self._chunks.keyword_search(
            workspace_id, request.query, request.document_id, leg_limit
        )
        keyword_ranked = [chunk.id for chunk, _ in keyword_hits]
        keyword_scores = {chunk.id: score for chunk, score in keyword_hits}

        semantic_hits = await self._semantic_leg(workspace_id, request, leg_limit)
        semantic_used = semantic_hits is not None
        semantic_ranked = [chunk_id for chunk_id, _ in semantic_hits or []]
        semantic_scores = dict(semantic_hits or [])

        fused = reciprocal_rank_fusion([keyword_ranked, semantic_ranked], k=self._settings.rrf_k)
        # deterministic order: fused score desc, then chunk id as tiebreak
        top_ids = sorted(fused, key=lambda cid: (-fused[cid], cid))[: request.top_k]

        chunks_by_id = {chunk.id: chunk for chunk in await self._chunks.get_by_ids(top_ids)}
        keyword_rank = {cid: i + 1 for i, cid in enumerate(keyword_ranked)}
        semantic_rank = {cid: i + 1 for i, cid in enumerate(semantic_ranked)}

        results = [
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                workspace_id=chunk.workspace_id,
                version_id=None,
                document_name=chunk.document.name,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                clause_id=chunk.clause_id,
                heading=chunk.heading,
                section_path=chunk.section_path,
                text=chunk.text,
                scores=SearchScores(
                    rrf=fused[chunk.id],
                    keyword_rank=keyword_rank.get(chunk.id),
                    keyword_score=keyword_scores.get(chunk.id),
                    semantic_rank=semantic_rank.get(chunk.id),
                    semantic_score=semantic_scores.get(chunk.id),
                ),
            )
            for chunk_id in top_ids
            if (chunk := chunks_by_id.get(chunk_id)) is not None
        ]
        return SearchResponse(
            query=request.query,
            workspace_id=workspace_id,
            document_id=request.document_id,
            top_k=request.top_k,
            semantic_used=semantic_used,
            results=results,
        )

    async def _semantic_leg(
        self, workspace_id: uuid.UUID, request: SearchRequest, leg_limit: int
    ) -> list[tuple[uuid.UUID, float]] | None:
        """Returns ranked semantic hits, or None when the leg is unavailable
        (no embedding key configured, or embedding/Qdrant failed at runtime)."""
        client = embeddings.get_embedding_client(self._settings)
        if client is None:
            return None
        try:
            vector = (await client.embed([request.query]))[0]
            return await vectorstore.search_chunk_vectors(
                self._settings, vector, workspace_id, request.document_id, leg_limit
            )
        except Exception:
            logger.exception("Semantic leg failed; falling back to keyword-only results")
            return None
