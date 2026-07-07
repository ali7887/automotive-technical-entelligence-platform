import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.models import Document, ProcessingJob


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_document(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        return document

    async def add_job(self, job: ProcessingJob) -> ProcessingJob:
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        return await self._session.get(Document, document_id)

    async def get_job(self, job_id: uuid.UUID) -> ProcessingJob | None:
        return await self._session.get(ProcessingJob, job_id)

    async def list_by_workspace(self, workspace_id: uuid.UUID) -> Sequence[Document]:
        result = await self._session.scalars(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc())
        )
        return result.all()
