import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atip_api.models.enums import (
    ActorType,
    EvidenceRisk,
    EvidenceStatus,
    ReviewAction,
    ReviewStatus,
)

# actions a client may submit; SET_STATUS and EXTRACTION_ARCHIVED are recorded
# by the API itself (PATCH edits / re-extraction), never submitted directly
SubmittableReviewAction = Literal[
    ReviewAction.START_REVIEW,
    ReviewAction.APPROVE,
    ReviewAction.REJECT,
    ReviewAction.REQUEST_REVISION,
    ReviewAction.COMMENT,
    ReviewAction.SET_RISK,
]


class EvidenceCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_id: uuid.UUID
    clause_id: str | None
    page_start: int
    page_end: int
    # verified verbatim (whitespace/case-normalized) against the chunk at extraction time
    quote: str


class ReviewEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_item_id: uuid.UUID
    action: ReviewAction
    previous_status: ReviewStatus
    next_status: ReviewStatus
    previous_risk: EvidenceRisk
    next_risk: EvidenceRisk
    comment: str | None
    actor_name: str
    actor_type: ActorType
    extra: dict[str, Any] | None
    created_at: datetime


class EvidenceItemRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    requirement_text: str
    status: EvidenceStatus
    risk: EvidenceRisk
    review_status: ReviewStatus
    archived_at: datetime | None
    # optimistic-lock version; send it back as expected_version to detect races
    version: int
    citations: list[EvidenceCitationRead]
    created_at: datetime
    updated_at: datetime


class EvidenceItemSummary(BaseModel):
    """Queue row: enough metadata to render the Review Queue without citations."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    requirement_text: str
    status: EvidenceStatus
    risk: EvidenceRisk
    review_status: ReviewStatus
    citation_count: int
    version: int
    created_at: datetime
    updated_at: datetime


class EvidenceQueuePage(BaseModel):
    items: list[EvidenceItemSummary]
    total: int
    limit: int
    offset: int


class EvidenceItemDetail(EvidenceItemRead):
    event_count: int
    last_event: ReviewEventRead | None


class ReviewRequest(BaseModel):
    action: SubmittableReviewAction
    actor_name: str = Field(min_length=1, max_length=120)
    actor_type: ActorType
    comment: str | None = None
    risk: EvidenceRisk | None = None
    # optimistic lock: when provided, the item must still be at this version
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_action_payload(self) -> Self:
        comment = (self.comment or "").strip()
        needs_comment = (ReviewAction.REJECT, ReviewAction.REQUEST_REVISION, ReviewAction.COMMENT)
        if self.action in needs_comment and not comment:
            raise ValueError(f"comment is required for action {self.action}")
        if self.action == ReviewAction.SET_RISK and self.risk is None:
            raise ValueError("risk is required for action SET_RISK")
        if self.action != ReviewAction.SET_RISK and self.risk is not None:
            raise ValueError("risk may only be set with action SET_RISK")
        self.comment = comment or None
        return self


class ReviewResponse(BaseModel):
    item: EvidenceItemRead
    event: ReviewEventRead


class EvidenceItemUpdate(BaseModel):
    """Reviewer-owned inline edits (Phase 4 table); at least one must be provided.

    These edits are audited: each change appends a review event. The workflow
    `review_status` cannot be changed here — use the review endpoint.
    """

    status: EvidenceStatus | None = None
    risk: EvidenceRisk | None = None
    actor_name: str = Field(default="anonymous", min_length=1, max_length=120)
    # optimistic lock: when provided, the item must still be at this version
    expected_version: int | None = Field(default=None, ge=1)


class EvidenceExtractResponse(BaseModel):
    document_id: uuid.UUID
    items: list[EvidenceItemRead]
    # requirements proposed by the model, before citation verification
    requirements_seen: int
    # proposed requirements dropped because no citation quote could be verified
    requirements_dropped: int
    citations_dropped: int
    # reviewed items preserved (archived) instead of deleted on re-extraction
    items_archived: int
    warnings: list[str]
    model: str


class EvidenceItemExport(EvidenceItemRead):
    history: list[ReviewEventRead] | None = None


class EvidenceMapExport(BaseModel):
    """JSON Evidence Map export; the Markdown export renders the same items."""

    workspace_id: uuid.UUID | None
    workspace_name: str | None
    generated_at: datetime
    include_history: bool = False
    items: list[EvidenceItemExport]
