from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import WorkspaceViewerDep
from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.schemas.search import SearchRequest, SearchResponse
from atip_api.services.retrieval import SearchService

router = APIRouter(prefix="/api", tags=["search"])


def get_search_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SearchService:
    return SearchService(session, get_settings())


ServiceDep = Annotated[SearchService, Depends(get_search_service)]


@router.post("/workspaces/{workspace_id}/search", response_model=SearchResponse)
async def search_workspace(
    access: WorkspaceViewerDep, request: SearchRequest, service: ServiceDep
) -> SearchResponse:
    """Hybrid retrieval: Postgres FTS + Qdrant semantic search fused with RRF."""
    return await service.search(access.workspace.id, request)
