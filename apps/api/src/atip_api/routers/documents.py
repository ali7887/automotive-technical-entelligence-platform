import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from atip_api.auth import (
    CurrentUserDep,
    WorkspaceEditorDep,
    WorkspaceViewerDep,
    authorize_workspace,
)
from atip_api.config import get_settings
from atip_api.db import get_session
from atip_api.models import WorkspaceRole
from atip_api.observability import get_request_id
from atip_api.processing.pipeline import process_document
from atip_api.queue import enqueue_process_document
from atip_api.schemas.document import DocumentRead, DocumentUploadResponse, JobRead
from atip_api.services.documents import DocumentService

router = APIRouter(prefix="/api", tags=["documents"])


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentService:
    return DocumentService(session, get_settings())


ServiceDep = Annotated[DocumentService, Depends(get_document_service)]
DbDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=202,
)
async def upload_document(
    access: WorkspaceEditorDep,
    file: UploadFile,
    service: ServiceDep,
    background_tasks: BackgroundTasks,
) -> DocumentUploadResponse:
    """Accepts the file, records a PENDING job, and hands processing to the
    queue worker (202: poll GET /api/jobs/{job_id} for progress). If the queue
    is disabled or unreachable, processing falls back to an in-process task."""
    document, job = await service.upload(access.workspace.id, file)
    queued = await enqueue_process_document(get_settings(), document.id, job.id, get_request_id())
    if not queued:
        background_tasks.add_task(process_document, document.id, job.id)
    return DocumentUploadResponse(
        document=DocumentRead.model_validate(document), job=JobRead.model_validate(job)
    )


@router.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentRead])
async def list_documents(access: WorkspaceViewerDep, service: ServiceDep) -> list[DocumentRead]:
    documents = await service.list_documents(access.workspace.id)
    return [DocumentRead.model_validate(doc) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> DocumentRead:
    document = await service.get_document(document_id)
    await authorize_workspace(
        db, user, document.workspace_id, WorkspaceRole.WORKSPACE_VIEWER, request=request
    )
    return DocumentRead.model_validate(document)


@router.get(
    "/documents/{document_id}/file",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_document_file(
    document_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> FileResponse:
    document, path = await service.get_document_file(document_id)
    await authorize_workspace(
        db, user, document.workspace_id, WorkspaceRole.WORKSPACE_VIEWER, request=request
    )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.name,
        content_disposition_type="inline",
    )


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    service: ServiceDep,
    db: DbDep,
) -> JobRead:
    job = await service.get_job(job_id)
    document = await service.get_document(job.document_id)
    await authorize_workspace(
        db, user, document.workspace_id, WorkspaceRole.WORKSPACE_VIEWER, request=request
    )
    # after authorization only: this can write (fails jobs a worker abandoned)
    await service.reconcile_stale_job(job)
    return JobRead.model_validate(job)
