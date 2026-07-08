import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from atip_api.models.enums import EvidenceRisk, EvidenceStatus


class EvidenceCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_id: uuid.UUID
    clause_id: str | None
    page_start: int
    page_end: int
    # verified verbatim (whitespace/case-normalized) against the chunk at extraction time
    quote: str


class EvidenceItemRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    requirement_text: str
    status: EvidenceStatus
    risk: EvidenceRisk
    citations: list[EvidenceCitationRead]
    created_at: datetime
    updated_at: datetime


class EvidenceItemUpdate(BaseModel):
    """Reviewer-owned fields; at least one must be provided."""

    status: EvidenceStatus | None = None
    risk: EvidenceRisk | None = None


class EvidenceExtractResponse(BaseModel):
    document_id: uuid.UUID
    items: list[EvidenceItemRead]
    # requirements proposed by the model, before citation verification
    requirements_seen: int
    # proposed requirements dropped because no citation quote could be verified
    requirements_dropped: int
    citations_dropped: int
    warnings: list[str]
    model: str


class EvidenceMapExport(BaseModel):
    """JSON Evidence Map export; the Markdown export renders the same items."""

    workspace_id: uuid.UUID
    workspace_name: str
    generated_at: datetime
    items: list[EvidenceItemRead]
