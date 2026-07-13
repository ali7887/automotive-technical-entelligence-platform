from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for typed application errors rendered as JSON."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class DocumentNotReadyError(AppError):
    status_code = 409
    code = "document_not_ready"


class ReviewTransitionError(AppError):
    status_code = 409
    code = "invalid_review_transition"


class GenerationDisabledError(AppError):
    status_code = 503
    code = "generation_disabled"


class GenerationFailedError(AppError):
    status_code = 502
    code = "generation_failed"


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )
