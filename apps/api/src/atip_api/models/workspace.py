import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atip_api.db import Base

if TYPE_CHECKING:
    from atip_api.models.auth import WorkspaceMember
    from atip_api.models.document import Document


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # tenant isolation: every workspace belongs to exactly one organization
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
