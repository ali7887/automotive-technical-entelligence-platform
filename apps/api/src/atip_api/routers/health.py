import asyncio
from pathlib import Path

import redis.asyncio as aioredis
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams
from sqlalchemy import text

from atip_api.config import Settings, get_settings
from atip_api.db import get_engine
from atip_api.schemas.health import HealthResponse, ServiceStatus

router = APIRouter(tags=["health"])

_API_ROOT = Path(__file__).resolve().parents[3]


def _first_line(exc: Exception) -> str:
    return str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__


def _alembic_head() -> str | None:
    try:
        config = AlembicConfig(str(_API_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_API_ROOT / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        return None


async def _check_postgres() -> ServiceStatus:
    try:
        async with get_engine().connect() as conn:
            revision = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar()
    except Exception as exc:
        return ServiceStatus(status="error", detail=_first_line(exc))
    if revision is None:
        return ServiceStatus(status="error", detail="reachable but not migrated")
    head = _alembic_head()
    if head is not None and revision != head:
        return ServiceStatus(
            status="error", detail=f"migrations out of date (db={revision}, head={head})"
        )
    return ServiceStatus(status="ok", detail=f"migrated (rev {revision})")


async def _check_redis(settings: Settings) -> ServiceStatus:
    client = aioredis.from_url(settings.redis_url)
    try:
        await client.ping()
        return ServiceStatus(status="ok")
    except Exception as exc:
        return ServiceStatus(status="error", detail=_first_line(exc))
    finally:
        await client.aclose()


async def _check_qdrant(settings: Settings) -> ServiceStatus:
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        info = await client.get_collection(settings.qdrant_collection)
        vectors = info.config.params.vectors
        # a plain VectorParams means a single unnamed vector; a dict means named vectors
        size = vectors.size if isinstance(vectors, VectorParams) else None
        if size != settings.embedding_dim:
            return ServiceStatus(
                status="error",
                detail=(
                    f"collection '{settings.qdrant_collection}' has dim {size}, "
                    f"expected {settings.embedding_dim}"
                ),
            )
        return ServiceStatus(
            status="ok", detail=f"collection '{settings.qdrant_collection}' (dim {size})"
        )
    except Exception as exc:
        return ServiceStatus(status="error", detail=_first_line(exc))
    finally:
        await client.close()


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(response: Response) -> HealthResponse:
    """E2E health: Postgres reachable+migrated, Redis PING, Qdrant collection + vector dim."""
    settings = get_settings()
    postgres, redis_status, qdrant = await asyncio.gather(
        _check_postgres(), _check_redis(settings), _check_qdrant(settings)
    )
    services = {"postgres": postgres, "redis": redis_status, "qdrant": qdrant}
    healthy = all(service.status == "ok" for service in services.values())
    if not healthy:
        response.status_code = 503
    return HealthResponse(status="ok" if healthy else "degraded", services=services)
