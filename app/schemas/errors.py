"""Standardised error response schemas."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Detailed error information returned in API error responses."""

    code: str
    message: str
    retryable: bool
    retry_after_seconds: int | None = None
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    """Wrapper for all API error responses."""

    error: ErrorDetail
