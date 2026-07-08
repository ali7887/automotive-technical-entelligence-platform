import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atip_api.db import Base
from atip_api.models.enums import EvidenceRisk, EvidenceStatus


class EvidenceItem(Base):
    """A requirement extracted from a document, backed by quote-verified citations.

    Only requirements with at least one validated citation are ever persisted;
    `status` and `risk` are reviewer-owned and editable via the API.
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
    risk: Mapped[EvidenceRisk] = mapped_column(
        Enum(EvidenceRisk, name="evidence_risk"), default=EvidenceRisk.UNRATED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    citations: Mapped[list["EvidenceCitation"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="EvidenceCitation.page_start"
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
