"""arq worker consuming document-processing jobs from Redis.

Run with: `uv run arq atip_api.worker.WorkerSettings` (the production worker
container runs this against the same image and env as the API).

Retry policy is explicit and lives here, not in framework defaults:
- deterministic input failures (PdfValidationError) are terminal on the first
  try (handled inside process_document);
- unexpected failures retry with linear backoff up to JOB_MAX_TRIES, then the
  job and document are marked FAILED (never left hanging);
- a worker crash mid-job leaves the arq job pending; it is re-run when a
  worker returns. If no worker ever returns, the API fails the DB job lazily
  after JOB_STALE_AFTER_SECONDS.

Every task restores the upload request's correlation id into the logging
contextvar, so worker log lines carry the same request_id as the API's.
"""

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings
from arq.worker import Retry

from atip_api.config import get_app_version, get_settings
from atip_api.db import get_engine
from atip_api.observability import configure_logging, reset_request_id, set_request_id
from atip_api.processing.pipeline import (
    UnexpectedProcessingError,
    mark_job_failed,
    process_document,
)

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_SECONDS = 10


async def process_document_task(
    ctx: dict[str, Any], document_id: str, job_id: str, request_id: str | None = None
) -> None:
    settings = get_settings()
    job_try = int(ctx.get("job_try") or 1)
    token = set_request_id(request_id)
    try:
        logger.info(
            "Worker processing document %s (job %s, try %d/%d)",
            document_id,
            job_id,
            job_try,
            settings.job_max_tries,
        )
        try:
            await process_document(
                uuid.UUID(document_id), uuid.UUID(job_id), fail_terminally=False
            )
        except UnexpectedProcessingError as exc:
            if job_try < settings.job_max_tries:
                defer = _RETRY_BACKOFF_SECONDS * job_try
                logger.warning(
                    "Job %s try %d/%d failed; retrying in %ds",
                    job_id,
                    job_try,
                    settings.job_max_tries,
                    defer,
                )
                raise Retry(defer=defer) from exc
            logger.error(
                "Job %s failed after %d tries; marking FAILED", job_id, settings.job_max_tries
            )
            await mark_job_failed(
                uuid.UUID(job_id),
                f"Failed after {settings.job_max_tries} attempts: {exc}",
            )
    finally:
        reset_request_id(token)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "ATIP worker online (version=%s, build_sha=%s, max_tries=%d, job_timeout=%ds)",
        get_app_version(),
        settings.build_sha,
        settings.job_max_tries,
        settings.job_timeout_seconds,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await get_engine().dispose()
    logger.info("ATIP worker shut down")


class WorkerSettings:
    """arq entrypoint (settings are read once at worker boot)."""

    functions = (process_document_task,)
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = get_settings().job_timeout_seconds
    # our task raises Retry only while job_try < JOB_MAX_TRIES, so arq's own
    # cap just needs to not get in the way (crash re-runs also consume tries)
    max_tries = get_settings().job_max_tries
    keep_result = 3600
