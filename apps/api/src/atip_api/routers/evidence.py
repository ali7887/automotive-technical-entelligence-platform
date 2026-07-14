import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import (
    CurrentUserDep,
    WorkspaceViewerDep,
    accessible_workspace_ids,
    authorize_workspace,
)
from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.errors import NotFoundError
from atip_api.models import Document, EvidenceItem, User, WorkspaceRole
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
DbDep = Annotated[AsyncSession, Depends(get_session)]


async def _authorize_document(
    db: AsyncSession,
    user: User,
    request: Request,
    document_id: uuid.UUID,
    minimum: WorkspaceRole,
) -> None:
    workspace_id = (
        await db.execute(select(Document.workspace_id).where(Document.id == document_id))
    ).scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(f"Document {document_id} not found")
    await authorize_workspace(db, user, workspace_id, minimum, request=request)


async def _authorize_item(
    db: AsyncSession,
    user: User,
    request: Request,
    item_id: uuid.UUID,
    minimum: WorkspaceRole,
) -> None:
    workspace_id = (
        await db.execute(select(EvidenceItem.workspace_id).where(EvidenceItem.id == item_id))
    ).scalar_one_or_none()
    if workspace_id is None:
        raise NotFoundError(f"Evidence item {item_id} not found")
    await authorize_workspace(db, user, workspace_id, minimum, request=request)


@router.post(
    "/documents/{document_id}/evidence/extract",
    response_model=EvidenceExtractResponse,
    status_code=201,
    dependencies=[rate_limited("extract", lambda s: s.rate_limit_extract_per_minute)],
)
async def extract_evidence(
    document_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> EvidenceExtractResponse:
    """Extract verified requirements. Unreviewed prior items are replaced;
    items with review state or history are archived, never deleted."""
    await _authorize_document(db, user, request, document_id, WorkspaceRole.WORKSPACE_EDITOR)
    return await service.extract(document_id)


@router.get("/workspaces/{workspace_id}/evidence", response_model=list[EvidenceItemRead])
async def list_evidence(
    access: WorkspaceViewerDep,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
) -> list[EvidenceItemRead]:
    return await service.list_items(access.workspace.id, document_id)


# NOTE: declared before /evidence/{item_id} so the literal path wins routing
@router.get("/evidence/review-queue", response_model=EvidenceQueuePage)
async def review_queue(
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
    workspace_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_archived: bool = False,
    sort: QueueSort = "updated_desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceQueuePage:
    """Paginated review queue; archived items are excluded unless requested.

    Tenant isolation: with a workspace_id the caller must be able to read that
    workspace; without one, results are restricted to the caller's readable
    workspaces."""
    workspace_ids: list[uuid.UUID] | None = None
    if workspace_id is not None:
        await authorize_workspace(
            db, user, workspace_id, WorkspaceRole.WORKSPACE_VIEWER, request=request
        )
    else:
        workspace_ids = await accessible_workspace_ids(db, user)
    return await service.queue(
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        document_id=document_id,
        review_status=review_status,
        risk=risk,
        include_archived=include_archived,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/evidence/{item_id}", response_model=EvidenceItemDetail)
async def get_evidence_item(
    item_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> EvidenceItemDetail:
    await _authorize_item(db, user, request, item_id, WorkspaceRole.WORKSPACE_VIEWER)
    return await service.detail(item_id)


@router.patch("/evidence/{item_id}", response_model=EvidenceItemRead)
async def update_evidence_item(
    item_id: uuid.UUID,
    patch: EvidenceItemUpdate,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> EvidenceItemRead:
    await _authorize_item(db, user, request, item_id, WorkspaceRole.WORKSPACE_EDITOR)
    return await service.update_item(item_id, patch)


@router.post("/evidence/{item_id}/review", response_model=ReviewResponse)
async def review_evidence_item(
    item_id: uuid.UUID,
    request: ReviewRequest,
    http_request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> ReviewResponse:
    """Apply one audited review action; invalid transitions return 409."""
    await _authorize_item(db, user, http_request, item_id, WorkspaceRole.WORKSPACE_EDITOR)
    return await service.review(item_id, request)


@router.get("/evidence/{item_id}/history", response_model=list[ReviewEventRead])
async def evidence_item_history(
    item_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> list[ReviewEventRead]:
    """Full append-only audit trail of the item, oldest first."""
    await _authorize_item(db, user, request, item_id, WorkspaceRole.WORKSPACE_VIEWER)
    return await service.history(item_id)


@router.get("/workspaces/{workspace_id}/evidence/export", response_model=EvidenceMapExport)
async def export_evidence_json(
    access: WorkspaceViewerDep,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_history: bool = False,
) -> EvidenceMapExport:
    return await service.export(
        access.workspace.id,
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
    access: WorkspaceViewerDep,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    risk: EvidenceRisk | None = None,
    include_history: bool = False,
) -> PlainTextResponse:
    export = await service.export(
        access.workspace.id,
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
