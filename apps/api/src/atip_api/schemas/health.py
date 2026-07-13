from typing import Literal

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    services: dict[str, ServiceStatus]


class LivenessResponse(BaseModel):
    """Process is up. No dependency checks — safe for orchestrator liveness probes."""

    status: Literal["ok"]
    version: str
    environment: str
    build_sha: str | None = None


class ReadinessResponse(BaseModel):
    """Can serve traffic. Postgres is required; Redis/Qdrant outages only degrade
    (keyword-only search keeps working), so they must not evict the instance."""

    status: Literal["ready", "degraded", "not_ready"]
    services: dict[str, ServiceStatus]
