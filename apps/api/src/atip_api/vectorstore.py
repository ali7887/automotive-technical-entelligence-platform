import logging
import uuid
from collections.abc import Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Condition,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from atip_api.config import Settings
from atip_api.models import Chunk

logger = logging.getLogger(__name__)


async def ensure_qdrant_collection(settings: Settings) -> None:
    """Idempotently create the chunk collection so /health can verify dimensions."""
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        if not await client.collection_exists(settings.qdrant_collection):
            await client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )
            logger.info(
                "Created Qdrant collection %r (dim=%d)",
                settings.qdrant_collection,
                settings.embedding_dim,
            )
        # payload indexes back the workspace/document filters used by retrieval
        for field in ("workspace_id", "document_id"):
            await client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
    finally:
        await client.close()


def chunk_payload(chunk: Chunk) -> dict[str, Any]:
    """Qdrant payload per docs/04_DATA_MODEL.md; must map back to the Postgres chunk."""
    return {
        "postgres_chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "workspace_id": str(chunk.workspace_id),
        "version_id": None,  # document versioning arrives in a later phase; never invented
        "clause_id": chunk.clause_id,
        "chunk_text": chunk.text,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "chunk_index": chunk.chunk_index,
    }


async def upsert_chunk_vectors(
    settings: Settings, items: Sequence[tuple[Chunk, list[float]]]
) -> None:
    """Upsert chunk vectors with stable point ids (= Postgres chunk UUIDs)."""
    if not items:
        return
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=[
                PointStruct(id=str(chunk.id), vector=vector, payload=chunk_payload(chunk))
                for chunk, vector in items
            ],
        )
    finally:
        await client.close()


async def delete_chunk_vectors(settings: Settings, chunk_ids: Sequence[uuid.UUID]) -> None:
    if not chunk_ids:
        return
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=PointIdsList(points=[str(chunk_id) for chunk_id in chunk_ids]),
        )
    finally:
        await client.close()


async def search_chunk_vectors(
    settings: Settings,
    vector: list[float],
    workspace_id: uuid.UUID,
    document_id: uuid.UUID | None,
    limit: int,
) -> list[tuple[uuid.UUID, float]]:
    """Semantic leg: ranked (chunk_id, cosine score) scoped to a workspace/document."""
    conditions: list[Condition] = [
        FieldCondition(key="workspace_id", match=MatchValue(value=str(workspace_id)))
    ]
    if document_id is not None:
        conditions.append(
            FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))
        )
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            query_filter=Filter(must=conditions),
            limit=limit,
            with_payload=False,
        )
    finally:
        await client.close()
    return [(uuid.UUID(str(point.id)), float(point.score)) for point in response.points]
