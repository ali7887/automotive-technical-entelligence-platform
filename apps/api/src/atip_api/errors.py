"""Typed application errors rendered as RFC 7807 problem details.

Every error response carries `type`, `title`, `status`, `detail`, `instance`
plus two extension members: `code` (stable machine-readable identifier, kept
from the pre-7807 API) and `request_id` (correlation id, also echoed in the
`X-Request-ID` response header). Unhandled exceptions are logged with their
traceback and returned as a masked generic 500 — internals never leak.
"""

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from atip_api.observability import get_request_id

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
# resolved against the request URI; a docs page can be mounted there later
_TYPE_PREFIX = "/errors/"


class AppError(Exception):
    """Base class for typed application errors rendered as problem details."""

    status_code = 500
    code = "internal_error"
    title = "Internal Server Error"

    def __init__(
        self,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.headers = headers
        self.extra = extra
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    title = "Not Found"


class AuthenticationRequiredError(AppError):
    status_code = 401
    code = "authentication_required"
    title = "Authentication Required"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    title = "Invalid Credentials"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    title = "Forbidden"


class AnswerNotFoundError(AppError):
    """Verification rejected every claim: the unverified draft is withheld."""

    status_code = 404
    code = "not_found"
    title = "No Verified Answer"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"
    title = "Unsupported File Type"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"
    title = "File Too Large"


class PdfCorruptedError(AppError):
    status_code = 422
    code = "pdf_corrupted"
    title = "Corrupted PDF"


class PdfEncryptedError(AppError):
    status_code = 422
    code = "pdf_encrypted"
    title = "Encrypted PDF"


class EmptyTextLayerError(AppError):
    status_code = 422
    code = "empty_text_layer"
    title = "No Extractable Text"


class DocumentNotReadyError(AppError):
    status_code = 409
    code = "document_not_ready"
    title = "Document Not Ready"


class ReviewTransitionError(AppError):
    status_code = 409
    code = "invalid_review_transition"
    title = "Invalid Review Transition"


class StaleVersionError(AppError):
    status_code = 409
    code = "stale_version"
    title = "Concurrent Modification"


class ExtractionInProgressError(AppError):
    status_code = 409
    code = "extraction_in_progress"
    title = "Extraction Already Running"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    title = "Too Many Requests"

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after)})


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    title = "Service Unavailable"


class GenerationDisabledError(AppError):
    status_code = 503
    code = "generation_disabled"
    title = "Generation Disabled"


class GenerationFailedError(AppError):
    status_code = 502
    code = "generation_failed"
    title = "Generation Failed"


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{_TYPE_PREFIX}{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "request_id": get_request_id(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(
        status_code=status, content=body, headers=headers, media_type=PROBLEM_CONTENT_TYPE
    )


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return problem_response(
        request,
        status=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.message,
        headers=exc.headers,
        extra=exc.extra,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # only client-safe fields; pydantic's ctx/url can carry exception objects
    errors = [
        {"loc": [str(part) for part in error.get("loc", [])], "msg": str(error.get("msg", ""))}
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="validation_error",
        title="Invalid Request",
        detail="One or more request parameters failed validation.",
        extra={"errors": errors},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return problem_response(
        request,
        status=exc.status_code,
        code="http_error",
        title="Request Failed",
        detail=str(exc.detail),
        headers=getattr(exc, "headers", None),
    )


async def db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    # connection-level DB failures (after retries) are transient: advertise 503
    logger.error(
        "Database unavailable on %s %s", request.method, request.url.path, exc_info=exc
    )
    return problem_response(
        request,
        status=503,
        code="service_unavailable",
        title="Service Unavailable",
        detail="The database is temporarily unavailable. Please retry shortly.",
        headers={"Retry-After": "5"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # full traceback stays in the structured log; the client gets a masked 500
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return problem_response(
        request,
        status=500,
        code="internal_error",
        title="Internal Server Error",
        detail="An unexpected error occurred. The incident was logged.",
    )
