"""Canonical error-code registry for DigiLocker Verification API.

Every application-level error maps to exactly one :class:`ErrorCode` member.
The companion dictionaries :data:`ERROR_HTTP_STATUS_MAP` and
:data:`ERROR_RETRYABLE_MAP` describe the HTTP semantics and retry policy for
each code so that error handlers and clients behave consistently.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ErrorCode", "ERROR_HTTP_STATUS_MAP", "ERROR_RETRYABLE_MAP"]


class ErrorCode(StrEnum):
    """Machine-readable error codes returned in API error responses."""

    VERIFICATION_ALREADY_IN_PROGRESS = "VERIFICATION_ALREADY_IN_PROGRESS"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_STATE = "INVALID_STATE"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TOKEN_EXCHANGE_FAILED = "TOKEN_EXCHANGE_FAILED"
    ID_TOKEN_INVALID = "ID_TOKEN_INVALID"
    JWKS_FETCH_FAILED = "JWKS_FETCH_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    VERIFICATION_NOT_FOUND = "VERIFICATION_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# HTTP status mapping
# ---------------------------------------------------------------------------

ERROR_HTTP_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.VERIFICATION_ALREADY_IN_PROGRESS: 409,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.INVALID_STATE: 400,
    ErrorCode.SESSION_EXPIRED: 400,
    ErrorCode.TOKEN_EXCHANGE_FAILED: 502,
    ErrorCode.ID_TOKEN_INVALID: 502,
    ErrorCode.JWKS_FETCH_FAILED: 502,
    ErrorCode.PROVIDER_UNAVAILABLE: 503,
    ErrorCode.VERIFICATION_NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.INTERNAL_ERROR: 500,
}

# ---------------------------------------------------------------------------
# Retryable flag mapping
# ---------------------------------------------------------------------------

ERROR_RETRYABLE_MAP: dict[ErrorCode, bool] = {
    ErrorCode.VERIFICATION_ALREADY_IN_PROGRESS: False,
    ErrorCode.RATE_LIMIT_EXCEEDED: True,
    ErrorCode.INVALID_STATE: False,
    ErrorCode.SESSION_EXPIRED: True,
    ErrorCode.TOKEN_EXCHANGE_FAILED: True,
    ErrorCode.ID_TOKEN_INVALID: False,
    ErrorCode.JWKS_FETCH_FAILED: True,
    ErrorCode.PROVIDER_UNAVAILABLE: True,
    ErrorCode.VERIFICATION_NOT_FOUND: False,
    ErrorCode.UNAUTHORIZED: False,
    ErrorCode.INTERNAL_ERROR: True,
}
