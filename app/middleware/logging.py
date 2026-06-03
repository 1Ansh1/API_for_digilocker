"""Structured request/response logging middleware.

Logs every HTTP request with method, path, status code, duration,
and correlation ID using ``structlog`` for machine-parseable output.
"""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log request metadata and response timing for every HTTP call.

    Binds the correlation ID (set by :class:`RequestIDMiddleware`) into
    the structlog context so that all log lines emitted during a single
    request share the same trace identifier.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Wrap the request lifecycle with structured logging."""
        correlation_id: str = getattr(
            request.state,
            "correlation_id",
            "unknown",
        )

        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        structlog.contextvars.unbind_contextvars("correlation_id")

        return response
