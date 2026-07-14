import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.models import Workspace


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, organization_id: uuid.UUID) -> Workspace:
        workspace = Workspace(name=name, organization_id=organization_id)
        self._session.add(workspace)
        await self._session.flush()
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self._session.get(Workspace, workspace_id)

    async def list_all(self) -> Sequence[Workspace]:
        result = await self._session.scalars(
            select(Workspace).order_by(Workspace.created_at.desc())
        )
        return result.all()

    async def delete(self, workspace: Workspace) -> None:
        await self._session.delete(workspace)
        await self._session.flush()
