import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atip_api.db import Base

if TYPE_CHECKING:
    from atip_api.models.document import Document

# Everything FTS should match: clause id, heading, and body text.
_TSVECTOR_SQL = (
    "to_tsvector('english', coalesce(clause_id, '') || ' ' || coalesce(heading, '') || ' ' || text)"
)


class Chunk(Base):
    """A retrieval unit extracted from a document page range.

    `id` is a deterministic UUIDv5 of (document_id, chunk_index, content_hash) and
    doubles as the Qdrant point ID, so re-processing an unchanged document is a no-op.
    """

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int]
    page_start: Mapped[int]
    page_end: Mapped[int]
    clause_id: Mapped[str | None] = mapped_column(String(64))
    heading: Mapped[str | None] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    text_search: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(_TSVECTOR_SQL, persisted=True), nullable=True
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        Index("ix_chunks_text_search", "text_search", postgresql_using="gin"),
    )
