import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from atip_api.config import Settings

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
    finally:
        await client.close()
