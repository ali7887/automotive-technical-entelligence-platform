import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from atip_api.models import Document, EvidenceItem


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_all(self, items: Sequence[EvidenceItem]) -> None:
        self._session.add_all(items)
        await self._session.flush()

    async def delete_by_document(self, document_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(EvidenceItem).where(EvidenceItem.document_id == document_id)
        )
        await self._session.flush()

    async def get(self, item_id: uuid.UUID) -> tuple[EvidenceItem, str] | None:
        row = (
            await self._session.execute(
                select(EvidenceItem, Document.name)
                .join(Document, EvidenceItem.document_id == Document.id)
                .options(selectinload(EvidenceItem.citations))
                .where(EvidenceItem.id == item_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def list_by_workspace(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID | None = None
    ) -> list[tuple[EvidenceItem, str]]:
        """Items with their document name, in stable citation-page order."""
        stmt = (
            select(EvidenceItem, Document.name)
            .join(Document, EvidenceItem.document_id == Document.id)
            .options(selectinload(EvidenceItem.citations))
            .where(EvidenceItem.workspace_id == workspace_id)
            .order_by(Document.name, EvidenceItem.created_at, EvidenceItem.id)
        )
        if document_id is not None:
            stmt = stmt.where(EvidenceItem.document_id == document_id)
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]
