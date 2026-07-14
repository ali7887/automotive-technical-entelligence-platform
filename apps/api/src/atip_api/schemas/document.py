import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from atip_api.models.enums import DocumentStatus, JobStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: DocumentStatus
    sha256: str | None
    page_count: int | None
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: JobStatus
    # progress: queued -> extracting -> vectorizing -> ready | failed
    stage: str | None
    attempts: int
    request_id: str | None
    error_message: str | None
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    job: JobRead
