import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.errors import NotFoundError
from atip_api.models import User, UserRole, Workspace, WorkspaceMember, WorkspaceRole
from atip_api.repositories.workspaces import WorkspaceRepository
from atip_api.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkspaceRepository(session)

    async def create(self, data: WorkspaceCreate, user: User) -> Workspace:
        """New workspaces live in the creator's org; the creator gets editor."""
        workspace = await self._repo.create(data.name, user.organization_id)
        self._session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.WORKSPACE_EDITOR,
            )
        )
        await self._session.commit()
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self._repo.get(workspace_id)
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    async def list_for(self, user: User) -> Sequence[Workspace]:
        """Tenant-scoped listing: memberships for members, the whole org for
        org admins, everything for platform admins."""
        stmt = select(Workspace).order_by(Workspace.created_at.desc())
        if user.role == UserRole.PLATFORM_ADMIN:
            pass
        elif user.role == UserRole.ORG_ADMIN:
            stmt = stmt.where(Workspace.organization_id == user.organization_id)
        else:
            stmt = stmt.join(
                WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id
            ).where(
                WorkspaceMember.user_id == user.id,
                Workspace.organization_id == user.organization_id,
            )
        return (await self._session.scalars(stmt)).all()

    async def rename(self, workspace_id: uuid.UUID, data: WorkspaceUpdate) -> Workspace:
        workspace = await self.get(workspace_id)
        workspace.name = data.name
        await self._session.commit()
        return workspace

    async def delete(self, workspace_id: uuid.UUID) -> None:
        workspace = await self.get(workspace_id)
        await self._repo.delete(workspace)
        await self._session.commit()
