"""Redis-backed ingestion queue (arq) with an in-process fallback.

arq over RQ/Celery/Dramatiq: the whole pipeline is already async (asyncpg,
AsyncQdrantClient, AsyncOpenAI), and arq runs coroutines natively in a single
asyncio process — no fork (works on Windows dev machines), no sync bridge, and
it reuses the redis dependency the stack already has.

The queue is opt-in (QUEUE_ENABLED): development and tests keep the in-process
BackgroundTasks behavior; production enables the queue and runs a dedicated
worker container. An enqueue failure never fails an upload — the router falls
back to in-process processing and logs the degradation.
"""

import contextlib
import logging
import uuid

from arq.connections import ArqRedis, RedisSettings, create_pool

from atip_api.config import Settings

logger = logging.getLogger(__name__)

PROCESS_DOCUMENT_TASK = "process_document_task"

_pool: ArqRedis | None = None


async def get_pool(settings: Settings) -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        with contextlib.suppress(Exception):
            await _pool.close()
        _pool = None


async def enqueue_process_document(
    settings: Settings,
    document_id: uuid.UUID,
    job_id: uuid.UUID,
    request_id: str | None,
) -> bool:
    """Enqueue a processing job; False means the caller must run it in-process."""
    if not settings.queue_enabled:
        return False
    try:
        pool = await get_pool(settings)
        # arq job id = DB job id: enqueueing the same job twice is a no-op
        await pool.enqueue_job(
            PROCESS_DOCUMENT_TASK,
            str(document_id),
            str(job_id),
            request_id,
            _job_id=str(job_id),
        )
        return True
    except Exception:
        logger.warning(
            "Queue unavailable; document %s will be processed in-process",
            document_id,
            exc_info=True,
        )
        await close_pool()  # drop the possibly-broken connection for next time
        return False
