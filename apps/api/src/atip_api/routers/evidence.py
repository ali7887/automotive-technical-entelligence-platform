import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.schemas.evidence import (
    EvidenceExtractResponse,
    EvidenceItemRead,
    EvidenceItemUpdate,
    EvidenceMapExport,
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
)
async def extract_evidence(
    document_id: uuid.UUID, service: ServiceDep
) -> EvidenceExtractResponse:
    """Extract verified requirements; replaces the document's existing evidence."""
    return await service.extract(document_id)


@router.get("/workspaces/{workspace_id}/evidence", response_model=list[EvidenceItemRead])
async def list_evidence(
    workspace_id: uuid.UUID,
    service: ServiceDep,
    document_id: uuid.UUID | None = None,
) -> list[EvidenceItemRead]:
    return await service.list_items(workspace_id, document_id)


@router.patch("/evidence/{item_id}", response_model=EvidenceItemRead)
async def update_evidence_item(
    item_id: uuid.UUID, patch: EvidenceItemUpdate, service: ServiceDep
) -> EvidenceItemRead:
    return await service.update_item(item_id, patch)


@router.get("/workspaces/{workspace_id}/evidence/export", response_model=EvidenceMapExport)
async def export_evidence_json(
    workspace_id: uuid.UUID, service: ServiceDep
) -> EvidenceMapExport:
    return await service.export(workspace_id)


@router.get(
    "/workspaces/{workspace_id}/evidence/export.md",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/markdown": {}}}},
)
async def export_evidence_markdown(
    workspace_id: uuid.UUID, service: ServiceDep
) -> PlainTextResponse:
    export = await service.export(workspace_id)
    return PlainTextResponse(
        export_markdown(export),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="evidence-map.md"'},
    )
