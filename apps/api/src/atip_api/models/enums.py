import enum


class DocumentStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class JobStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class EvidenceStatus(enum.StrEnum):
    """Reviewer-owned compliance status of an extracted requirement."""

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceRisk(enum.StrEnum):
    """Reviewer-owned risk rating of an extracted requirement."""

    UNRATED = "UNRATED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReviewStatus(enum.StrEnum):
    """Workflow state of the human review of an extracted evidence item.

    Orthogonal to EvidenceStatus (compliance verdict): this tracks whether a
    human has reviewed the extraction itself.
    """

    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"


class ReviewAction(enum.StrEnum):
    """Actions recorded in the append-only review audit trail."""

    START_REVIEW = "START_REVIEW"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"
    COMMENT = "COMMENT"
    SET_RISK = "SET_RISK"
    # compliance-status inline edit via PATCH (Phase 4 Evidence Map table)
    SET_STATUS = "SET_STATUS"
    # system event: item archived because the document was re-extracted
    EXTRACTION_ARCHIVED = "EXTRACTION_ARCHIVED"


class ActorType(enum.StrEnum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
