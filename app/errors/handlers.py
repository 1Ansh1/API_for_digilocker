"""FastAPI exception handlers for structured error responses.

Registers handlers for :class:`DigiLockerError`, validation errors, and
unhandled exceptions so every error response follows the canonical format::

    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human-readable message",
            "retryable": false,
            "retry_after_seconds": null,
            "correlation_id": "req-abc123"
        }
    }
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors.codes import ErrorCode
from app.errors.exceptions import DigiLockerError

logger = logging.getLogger(__name__)

__all__ = ["register_exception_handlers"]


def _get_correlation_id(request: Request) -> str | None:
    """Extract the correlation ID from request state if available."""
    return getattr(request.state, "correlation_id", None)


async def _handle_digilocker_error(
    request: Request,
    exc: DigiLockerError,
) -> JSONResponse:
    """Handle application-level DigiLocker errors."""
    correlation_id = _get_correlation_id(request)

    logger.warning(
        "DigiLocker error: %s [%s] correlation_id=%s",
        exc.error_code,
        exc.message,
        correlation_id,
    )

    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": {
                "code": exc.error_code.value,
                "message": exc.message,
                "retryable": exc.retryable,
                "retry_after_seconds": exc.retry_after_seconds,
                "correlation_id": correlation_id,
            }
        },
    )


async def _handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic / FastAPI request validation errors."""
    correlation_id = _get_correlation_id(request)

    # Collapse validation details into a single message
    details = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": f"Request validation failed: {details}",
                "retryable": False,
                "retry_after_seconds": None,
                "correlation_id": correlation_id,
            }
        },
    )


async def _handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all handler for unexpected exceptions."""
    correlation_id = _get_correlation_id(request)

    logger.exception(
        "Unhandled exception correlation_id=%s",
        correlation_id,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected internal error occurred.",
                "retryable": True,
                "retry_after_seconds": None,
                "correlation_id": correlation_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the FastAPI application."""
    app.add_exception_handler(DigiLockerError, _handle_digilocker_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unhandled_exception)
