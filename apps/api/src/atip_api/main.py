import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atip_api.config import get_settings
from atip_api.db import get_engine
from atip_api.errors import AppError, app_error_handler
from atip_api.routers.documents import router as documents_router
from atip_api.routers.health import router as health_router
from atip_api.routers.workspaces import router as workspaces_router
from atip_api.vectorstore import ensure_qdrant_collection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        await ensure_qdrant_collection(settings)
    except Exception:
        # Startup must not depend on Qdrant; /health surfaces the failure.
        logger.warning("Could not ensure Qdrant collection at startup", exc_info=True)
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ATIP API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(health_router)
    app.include_router(workspaces_router)
    app.include_router(documents_router)
    return app


app = create_app()
