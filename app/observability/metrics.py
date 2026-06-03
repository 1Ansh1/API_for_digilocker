"""Prometheus metrics definitions for DigiLocker Verification API.

All domain-specific metrics are prefixed with ``digilocker_`` and defined
as module-level constants so they can be imported and used anywhere in the
application without additional setup.

A :func:`setup_metrics_endpoint` helper returns a ready-made Starlette
:class:`Route` that serves the ``/metrics`` scrape endpoint.
"""

from __future__ import annotations

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

__all__ = [
    "VERIFICATIONS_TOTAL",
    "VERIFICATION_DURATION",
    "TOKEN_EXCHANGE_DURATION",
    "CALLBACK_PROCESSING_DURATION",
    "ACTIVE_SESSIONS",
    "RATE_LIMIT_HITS",
    "JWKS_CACHE_HITS",
    "JWKS_CACHE_MISSES",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION",
    "setup_metrics_endpoint",
]

# ---------------------------------------------------------------------------
# Domain metrics
# ---------------------------------------------------------------------------

VERIFICATIONS_TOTAL: Counter = Counter(
    name="digilocker_verifications_total",
    documentation="Total number of verification attempts partitioned by final status.",
    labelnames=("status",),
)

VERIFICATION_DURATION: Histogram = Histogram(
    name="digilocker_verification_duration_seconds",
    documentation="End-to-end verification duration in seconds.",
    labelnames=("status",),
)

TOKEN_EXCHANGE_DURATION: Histogram = Histogram(
    name="digilocker_token_exchange_duration_seconds",
    documentation="Time spent exchanging an authorization code for tokens.",
    labelnames=("status",),
)

CALLBACK_PROCESSING_DURATION: Histogram = Histogram(
    name="digilocker_callback_processing_duration_seconds",
    documentation="Time spent processing the OAuth callback.",
)

ACTIVE_SESSIONS: Gauge = Gauge(
    name="digilocker_active_sessions",
    documentation="Number of currently active OAuth sessions.",
)

RATE_LIMIT_HITS: Counter = Counter(
    name="digilocker_rate_limit_hits_total",
    documentation="Number of requests rejected by rate limiting.",
    labelnames=("type",),
)

JWKS_CACHE_HITS: Counter = Counter(
    name="digilocker_jwks_cache_hits_total",
    documentation="Number of JWKS lookups served from cache.",
)

JWKS_CACHE_MISSES: Counter = Counter(
    name="digilocker_jwks_cache_misses_total",
    documentation="Number of JWKS lookups that required a remote fetch.",
)

# ---------------------------------------------------------------------------
# HTTP-layer metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL: Counter = Counter(
    name="http_requests_total",
    documentation="Total HTTP requests received.",
    labelnames=("method", "path", "status"),
)

HTTP_REQUEST_DURATION: Histogram = Histogram(
    name="http_request_duration_seconds",
    documentation="HTTP request latency in seconds.",
    labelnames=("method", "path"),
)

# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------


async def _metrics_handler(request: Request) -> Response:
    """Serve Prometheus metrics in the text exposition format."""
    body = generate_latest(REGISTRY)
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def setup_metrics_endpoint() -> Route:
    """Return a Starlette :class:`Route` that exposes ``/metrics``.

    Usage::

        from starlette.routing import Mount
        app.routes.append(setup_metrics_endpoint())
    """
    return Route("/metrics", endpoint=_metrics_handler, methods=["GET"])
