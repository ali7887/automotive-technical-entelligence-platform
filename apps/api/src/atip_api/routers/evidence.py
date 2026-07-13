import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.models.enums import EvidenceRisk, ReviewStatus
from atip_api.ratelimit import rate_limited
from atip_api.repositories.evidence import QueueSort
from atip_api.schemas.evidence import (
    EvidenceExtractResponse,
    EvidenceItemDetail,
    EvidenceItemRead,
    EvidenceItemUpdate,
    EvidenceMapExport,
    EvidenceQueuePage,
    ReviewEventRead,
    ReviewRequest,
    ReviewResponse,
)
from atip_api.services.evidence import EvidenceService, export_markdown

router = APIRouter(prefix="/api", tags=["evidence"])


def get_evidence_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvidenceService:
    return EvidenceService(session, get_settings())


ServiceDep = Annotated[EvidenceService, Depends(get_evidence_service)]


@router.post(
    "/documents/{document_id}/evidence/extract",
    response_model=EvidenceExtractResponse,
    status_code=201,
    dependencies=[rate_limited("extract", lambda s: s.rate_limit_extract_per_minute)],
)
async def extract_evidence(document_id: uuid.UUID, service: ServiceDep) -> EvidenceExtractResponse:
    """Extract verified requirements. Unreviewed prior items are replaced;
    items with review state or history are archived, never deleted."""
    return await service.extract(document_id)


@router.get("/workspaces/{workspace_id}/evidence", response_model=list[EvidenceItemRead])
async def list_evidence(
    workspace_id: uuid.UUID,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
) -> list[EvidenceItemRead]:
    return await service.list_items(workspace_id, document_id)


# NOTE: declared before /evidence/{item_id} so the literal path wins routing
@router.get("/evidence/review-queue", response_model=EvidenceQueuePage)
async def review_queue(
    service: ServiceDep,
    workspace_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_archived: bool = False,
    sort: QueueSort = "updated_desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceQueuePage:
    """Paginated review queue; archived items are excluded unless requested."""
    return await service.queue(
        workspace_id=workspace_id,
        document_id=document_id,
        review_status=review_status,
        risk=risk,
        include_archived=include_archived,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/evidence/{item_id}", response_model=EvidenceItemDetail)
async def get_evidence_item(item_id: uuid.UUID, service: ServiceDep) -> EvidenceItemDetail:
    return await service.detail(item_id)


@router.patch("/evidence/{item_id}", response_model=EvidenceItemRead)
async def update_evidence_item(
    item_id: uuid.UUID, patch: EvidenceItemUpdate, service: ServiceDep
) -> EvidenceItemRead:
    return await service.update_item(item_id, patch)


@router.post("/evidence/{item_id}/review", response_model=ReviewResponse)
async def review_evidence_item(
    item_id: uuid.UUID, request: ReviewRequest, service: ServiceDep
) -> ReviewResponse:
    """Apply one audited review action; invalid transitions return 409."""
    return await service.review(item_id, request)


@router.get("/evidence/{item_id}/history", response_model=list[ReviewEventRead])
async def evidence_item_history(item_id: uuid.UUID, service: ServiceDep) -> list[ReviewEventRead]:
    """Full append-only audit trail of the item, oldest first."""
    return await service.history(item_id)


@router.get("/workspaces/{workspace_id}/evidence/export", response_model=EvidenceMapExport)
async def export_evidence_json(
    workspace_id: uuid.UUID,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_history: bool = False,
) -> EvidenceMapExport:
    return await service.export(
        workspace_id,
        document_id=document_id,
        review_status=review_status,
        risk=risk,
        include_history=include_history,
    )


@router.get(
    "/workspaces/{workspace_id}/evidence/export.md",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/markdown": {}}}},
)
async def export_evidence_markdown(
    workspace_id: uuid.UUID,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_history: bool = False,
) -> PlainTextResponse:
    export = await service.export(
        workspace_id,
        document_id=document_id,
        review_status=review_status,
        risk=risk,
        include_history=include_history,
    )
    return PlainTextResponse(
        export_markdown(export),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="evidence-map.md"'},
    )
