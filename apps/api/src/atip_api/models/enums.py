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
