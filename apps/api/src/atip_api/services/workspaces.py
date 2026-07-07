import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.errors import NotFoundError
from atip_api.models import Workspace
from atip_api.repositories.workspaces import WorkspaceRepository
from atip_api.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkspaceRepository(session)

    async def create(self, data: WorkspaceCreate) -> Workspace:
        workspace = await self._repo.create(data.name)
        await self._session.commit()
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self._repo.get(workspace_id)
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    async def list_all(self) -> Sequence[Workspace]:
        return await self._repo.list_all()

    async def rename(self, workspace_id: uuid.UUID, data: WorkspaceUpdate) -> Workspace:
        workspace = await self.get(workspace_id)
        workspace.name = data.name
        await self._session.commit()
        return workspace

    async def delete(self, workspace_id: uuid.UUID) -> None:
        workspace = await self.get(workspace_id)
        await self._repo.delete(workspace)
        await self._session.commit()
