import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atip_api.db import Base
from atip_api.models.enums import (
    ActorType,
    EvidenceRisk,
    EvidenceStatus,
    ReviewAction,
    ReviewStatus,
)

# shared type objects so tables reusing a Postgres enum don't try to re-create it
_EVIDENCE_RISK_ENUM = Enum(EvidenceRisk, name="evidence_risk")
_REVIEW_STATUS_ENUM = Enum(ReviewStatus, name="review_status")


class EvidenceItem(Base):
    """A requirement extracted from a document, backed by quote-verified citations.

    Only requirements with at least one validated citation are ever persisted;
    `status` and `risk` are reviewer-owned and editable via the API.
    `review_status` tracks the human review workflow (Phase 5) and only changes
    through audited review actions.
    """

    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    requirement_text: Mapped[str] = mapped_column(Text)
    status: Mapped[EvidenceStatus] = mapped_column(
        Enum(EvidenceStatus, name="evidence_status"), default=EvidenceStatus.OPEN
    )
    risk: Mapped[EvidenceRisk] = mapped_column(_EVIDENCE_RISK_ENUM, default=EvidenceRisk.UNRATED)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _REVIEW_STATUS_ENUM, default=ReviewStatus.NEW, index=True
    )
    # set when re-extraction supersedes a reviewed item; archived items keep
    # their citations and audit trail but leave the queue and exports
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    citations: Mapped[list["EvidenceCitation"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="EvidenceCitation.page_start"
    )
    review_events: Mapped[list["EvidenceReviewEvent"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="EvidenceReviewEvent.seq",
    )


class EvidenceCitation(Base):
    """Provenance snapshot of one verified quote supporting an evidence item.

    Chunk metadata (clause, pages, quote) is copied at verification time and
    `chunk_id` is deliberately not a foreign key: re-processing a document must
    never silently delete recorded evidence provenance.
    """

    __tablename__ = "evidence_citations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    clause_id: Mapped[str | None] = mapped_column(String(64))
    page_start: Mapped[int]
    page_end: Mapped[int]
    # verified verbatim (whitespace/case-normalized) against the chunk text
    quote: Mapped[str] = mapped_column(Text)

    item: Mapped[EvidenceItem] = relationship(back_populates="citations")


class EvidenceReviewEvent(Base):
    """Append-only audit trail of review mutations on an evidence item.

    Rows are only ever inserted — never updated or deleted (except via the
    owning item's cascade). Review state on EvidenceItem is a snapshot; this
    table is the source of truth for how it got there.
    """

    __tablename__ = "evidence_review_events"
    __table_args__ = (Index("ix_evidence_review_events_item_seq", "evidence_item_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # monotonic order: events in one transaction share created_at, so the
    # timestamp alone cannot order an audit timeline deterministically
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[ReviewAction] = mapped_column(Enum(ReviewAction, name="review_action"))
    previous_status: Mapped[ReviewStatus] = mapped_column(_REVIEW_STATUS_ENUM)
    next_status: Mapped[ReviewStatus] = mapped_column(_REVIEW_STATUS_ENUM)
    previous_risk: Mapped[EvidenceRisk] = mapped_column(_EVIDENCE_RISK_ENUM)
    next_risk: Mapped[EvidenceRisk] = mapped_column(_EVIDENCE_RISK_ENUM)
    comment: Mapped[str | None] = mapped_column(Text)
    actor_name: Mapped[str] = mapped_column(String(120))
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type"))
    # extra context that has no dedicated column (e.g. compliance-status edits)
    extra: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[EvidenceItem] = relationship(back_populates="review_events")
