import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.db import get_session
from atip_api.schemas.workspace import WorkspaceCreate, WorkspaceRead, WorkspaceUpdate
from atip_api.services.workspaces import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def get_workspace_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceService:
    return WorkspaceService(session)


ServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]


@router.post("", response_model=WorkspaceRead, status_code=201)
async def create_workspace(data: WorkspaceCreate, service: ServiceDep) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.create(data))


@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(service: ServiceDep) -> list[WorkspaceRead]:
    return [WorkspaceRead.model_validate(ws) for ws in await service.list_all()]


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(workspace_id: uuid.UUID, service: ServiceDep) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.get(workspace_id))


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def rename_workspace(
    workspace_id: uuid.UUID, data: WorkspaceUpdate, service: ServiceDep
) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.rename(workspace_id, data))


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: uuid.UUID, service: ServiceDep) -> None:
    await service.delete(workspace_id)
