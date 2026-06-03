"""Request ID / correlation ID middleware.

Ensures every request carries a unique correlation ID that is
propagated through logs, audit events, and response headers.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request/response cycle.

    Behaviour:
        1. If the incoming request includes an ``X-Request-ID`` header,
           that value is reused as the correlation ID.
        2. Otherwise a new UUID4 is generated.
        3. The correlation ID is stored on ``request.state.correlation_id``
           for downstream consumers (loggers, audit repositories, etc.).
        4. The ``X-Request-ID`` header is added to every response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process the request and inject the correlation ID."""
        correlation_id = request.headers.get(
            "X-Request-ID",
            str(uuid.uuid4()),
        )

        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id

        return response
