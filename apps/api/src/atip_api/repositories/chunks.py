import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from atip_api.models import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_all(self, chunks: Sequence[Chunk]) -> None:
        self._session.add_all(chunks)
        await self._session.flush()

    async def list_by_document(self, document_id: uuid.UUID) -> Sequence[Chunk]:
        result = await self._session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return result.all()

    async def get_by_ids(self, chunk_ids: Sequence[uuid.UUID]) -> Sequence[Chunk]:
        if not chunk_ids:
            return []
        result = await self._session.scalars(
            select(Chunk).options(joinedload(Chunk.document)).where(Chunk.id.in_(chunk_ids))
        )
        return result.all()

    async def delete_by_ids(self, chunk_ids: Sequence[uuid.UUID]) -> None:
        if not chunk_ids:
            return
        await self._session.execute(delete(Chunk).where(Chunk.id.in_(chunk_ids)))
        await self._session.flush()

    async def mark_embedded(self, chunk_ids: Sequence[uuid.UUID], when: datetime) -> None:
        if not chunk_ids:
            return
        await self._session.execute(
            update(Chunk).where(Chunk.id.in_(chunk_ids)).values(embedded_at=when)
        )
        await self._session.flush()

    async def keyword_search(
        self,
        workspace_id: uuid.UUID,
        query: str,
        document_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[Chunk, float]]:
        """Keyword leg: Postgres FTS ranked by ts_rank_cd, deterministic tiebreak on id."""
        tsquery = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(Chunk.text_search, tsquery).label("rank")
        stmt = (
            select(Chunk, rank)
            .where(Chunk.workspace_id == workspace_id, Chunk.text_search.op("@@")(tsquery))
            .order_by(rank.desc(), Chunk.id.asc())
            .limit(limit)
        )
        if document_id is not None:
            stmt = stmt.where(Chunk.document_id == document_id)
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]
