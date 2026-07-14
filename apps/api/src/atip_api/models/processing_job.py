import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atip_api.db import Base
from atip_api.models.enums import JobStatus

if TYPE_CHECKING:
    from atip_api.models.document import Document


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.PENDING
    )
    # display-granularity progress: queued -> extracting -> vectorizing -> ready/failed
    stage: Mapped[str | None] = mapped_column(String(32))
    # processing attempts consumed (inline run or worker try)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    # correlation id of the originating upload request; carried into worker logs
    request_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="jobs")
