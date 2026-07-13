import uuid
from pathlib import Path

import anyio.to_thread
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.config import Settings
from atip_api.errors import FileTooLargeError, NotFoundError, UnsupportedFileTypeError
from atip_api.models import Document, ProcessingJob
from atip_api.processing.pdf_checks import precheck_pdf
from atip_api.repositories.documents import DocumentRepository
from atip_api.repositories.workspaces import WorkspaceRepository

_UPLOAD_CHUNK_SIZE = 1024 * 1024


class DocumentService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repo = DocumentRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def upload(
        self, workspace_id: uuid.UUID, file: UploadFile
    ) -> tuple[Document, ProcessingJob]:
        if await self._workspaces.get(workspace_id) is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        filename = file.filename or ""
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedFileTypeError("Only PDF files are supported")

        document_id = uuid.uuid4()
        storage_dir = self._settings.storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        target = storage_dir / f"{document_id}.pdf"

        written = 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                    written += len(chunk)
                    if written > self._settings.max_upload_bytes:
                        raise FileTooLargeError(
                            f"File exceeds the {self._settings.max_upload_mb} MB upload limit"
                        )
                    out.write(chunk)
            # reject corrupt/encrypted/scanned PDFs before a document exists;
            # pypdf blocks, so it runs off the event loop
            await anyio.to_thread.run_sync(
                precheck_pdf, target, self._settings.max_pdf_pages
            )
        except BaseException:
            target.unlink(missing_ok=True)
            raise

        document = await self._repo.add_document(
            Document(
                id=document_id,
                workspace_id=workspace_id,
                name=filename,
                storage_path=str(target),
            )
        )
        job = await self._repo.add_job(ProcessingJob(document_id=document.id))
        await self._session.commit()
        return document, job

    async def get_document(self, document_id: uuid.UUID) -> Document:
        document = await self._repo.get_document(document_id)
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        return document

    async def get_document_file(self, document_id: uuid.UUID) -> tuple[Document, Path]:
        document = await self.get_document(document_id)
        path = Path(document.storage_path)
        if not path.is_file():
            raise NotFoundError(f"Stored file for document {document_id} not found")
        return document, path

    async def get_job(self, job_id: uuid.UUID) -> ProcessingJob:
        job = await self._repo.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Processing job {job_id} not found")
        return job

    async def list_documents(self, workspace_id: uuid.UUID) -> list[Document]:
        if await self._workspaces.get(workspace_id) is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return list(await self._repo.list_by_workspace(workspace_id))
