from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import CurrentUserDep, WorkspaceEditorDep, WorkspaceViewerDep
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
async def create_workspace(
    data: WorkspaceCreate, user: CurrentUserDep, service: ServiceDep
) -> WorkspaceRead:
    """Creates the workspace in the caller's organization; the caller becomes
    a workspace editor."""
    return WorkspaceRead.model_validate(await service.create(data, user))


@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(user: CurrentUserDep, service: ServiceDep) -> list[WorkspaceRead]:
    """Only workspaces the caller can read: their memberships, or all
    organization workspaces for org admins."""
    return [WorkspaceRead.model_validate(ws) for ws in await service.list_for(user)]


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(access: WorkspaceViewerDep) -> WorkspaceRead:
    return WorkspaceRead.model_validate(access.workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def rename_workspace(
    data: WorkspaceUpdate, access: WorkspaceEditorDep, service: ServiceDep
) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.rename(access.workspace.id, data))


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(access: WorkspaceEditorDep, service: ServiceDep) -> None:
    await service.delete(access.workspace.id)
