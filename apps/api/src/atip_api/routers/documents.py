import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.processing.pipeline import process_document
from atip_api.schemas.document import DocumentRead, DocumentUploadResponse, JobRead
from atip_api.services.documents import DocumentService

router = APIRouter(prefix="/api", tags=["documents"])


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentService:
    return DocumentService(session, get_settings())


ServiceDep = Annotated[DocumentService, Depends(get_document_service)]


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile,
    service: ServiceDep,
    background_tasks: BackgroundTasks,
) -> DocumentUploadResponse:
    document, job = await service.upload(workspace_id, file)
    background_tasks.add_task(process_document, document.id, job.id)
    return DocumentUploadResponse(
        document=DocumentRead.model_validate(document), job=JobRead.model_validate(job)
    )


@router.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentRead])
async def list_documents(workspace_id: uuid.UUID, service: ServiceDep) -> list[DocumentRead]:
    return [DocumentRead.model_validate(doc) for doc in await service.list_documents(workspace_id)]


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, service: ServiceDep) -> DocumentRead:
    return DocumentRead.model_validate(await service.get_document(document_id))


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: uuid.UUID, service: ServiceDep) -> JobRead:
    return JobRead.model_validate(await service.get_job(job_id))
