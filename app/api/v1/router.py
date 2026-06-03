"""Aggregated API v1 router.

All v1 sub-routers are included here so that ``main.py`` only needs to
mount a single router for the entire version.
"""

from fastapi import APIRouter

from app.api.v1 import health, verification

__all__ = ["api_v1_router", "root_health_router"]

# ---------------------------------------------------------------------------
# Versioned API router
# ---------------------------------------------------------------------------

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router, prefix="/health", tags=["health"])
api_v1_router.include_router(
    verification.router,
    prefix="/verification",
    tags=["verification"],
)

# Future sub-routers:
# api_v1_router.include_router(callback.router, prefix="/callback", tags=["callback"])

# ---------------------------------------------------------------------------
# Root health router (for Kubernetes probes at /health/*)
# ---------------------------------------------------------------------------

root_health_router = APIRouter(prefix="/health", tags=["health"])
root_health_router.include_router(health.router)
