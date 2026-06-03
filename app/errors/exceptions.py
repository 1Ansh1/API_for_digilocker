"""Custom exception classes for DigiLocker Verification API.

Each exception maps to an :class:`~app.errors.codes.ErrorCode` and carries
the metadata needed by the exception handlers to build a structured JSON
error response.
"""

from __future__ import annotations

from app.errors.codes import ERROR_HTTP_STATUS_MAP, ERROR_RETRYABLE_MAP, ErrorCode

__all__ = [
    "DigiLockerError",
    "VerificationAlreadyInProgressError",
    "RateLimitExceededError",
    "InvalidStateError",
    "SessionExpiredError",
    "TokenExchangeError",
    "IdTokenInvalidError",
    "JWKSFetchError",
    "ProviderUnavailableError",
    "VerificationNotFoundError",
    "UnauthorizedError",
]


class DigiLockerError(Exception):
    """Base exception for all DigiLocker verification errors.

    Attributes:
        error_code: Machine-readable error code from :class:`ErrorCode`.
        message: Human-readable error description.
        retryable: Whether the client should retry the request.
        retry_after_seconds: Optional hint for retry delay.
        http_status: HTTP status code derived from the error code registry.
    """

    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return ERROR_RETRYABLE_MAP.get(self.error_code, False)

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS_MAP.get(self.error_code, 500)


class VerificationAlreadyInProgressError(DigiLockerError):
    """Raised when a user already has an active verification flow."""

    error_code = ErrorCode.VERIFICATION_ALREADY_IN_PROGRESS

    def __init__(
        self,
        message: str = "A verification flow is already active for this user.",
    ) -> None:
        super().__init__(message)


class RateLimitExceededError(DigiLockerError):
    """Raised when rate limit is exceeded."""

    error_code = ErrorCode.RATE_LIMIT_EXCEEDED

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message, retry_after_seconds=retry_after_seconds)


class InvalidStateError(DigiLockerError):
    """Raised when the OAuth state parameter does not match."""

    error_code = ErrorCode.INVALID_STATE

    def __init__(self, message: str = "Invalid or mismatched OAuth state parameter.") -> None:
        super().__init__(message)


class SessionExpiredError(DigiLockerError):
    """Raised when the OAuth session has expired in Redis."""

    error_code = ErrorCode.SESSION_EXPIRED

    def __init__(
        self,
        message: str = "OAuth session has expired. Please initiate a new verification.",
    ) -> None:
        super().__init__(message)


class TokenExchangeError(DigiLockerError):
    """Raised when the token exchange with DigiLocker fails."""

    error_code = ErrorCode.TOKEN_EXCHANGE_FAILED

    def __init__(self, message: str = "Failed to exchange authorization code for tokens.") -> None:
        super().__init__(message)


class IdTokenInvalidError(DigiLockerError):
    """Raised when the ID token signature or claims are invalid."""

    error_code = ErrorCode.ID_TOKEN_INVALID

    def __init__(self, message: str = "ID token validation failed.") -> None:
        super().__init__(message)


class JWKSFetchError(DigiLockerError):
    """Raised when JWKS keys cannot be fetched from the provider."""

    error_code = ErrorCode.JWKS_FETCH_FAILED

    def __init__(self, message: str = "Could not fetch JWKS from DigiLocker.") -> None:
        super().__init__(message)


class ProviderUnavailableError(DigiLockerError):
    """Raised when DigiLocker is unreachable."""

    error_code = ErrorCode.PROVIDER_UNAVAILABLE

    def __init__(self, message: str = "DigiLocker service is currently unavailable.") -> None:
        super().__init__(message)


class VerificationNotFoundError(DigiLockerError):
    """Raised when a verification ID does not exist."""

    error_code = ErrorCode.VERIFICATION_NOT_FOUND

    def __init__(self, message: str = "Verification not found.") -> None:
        super().__init__(message)


class UnauthorizedError(DigiLockerError):
    """Raised when the caller's JWT is missing or invalid."""

    error_code = ErrorCode.UNAUTHORIZED

    def __init__(self, message: str = "Missing or invalid authentication credentials.") -> None:
        super().__init__(message)
