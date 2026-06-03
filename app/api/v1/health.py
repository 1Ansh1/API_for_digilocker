"""Health-check endpoints for liveness, readiness and startup probes.

These are intended for Kubernetes / load-balancer health checks but work
equally well for manual verification during development.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

__all__ = ["router"]

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    """Possible top-level health states."""

    ALIVE = "alive"
    READY = "ready"
    DEGRADED = "degraded"
    STARTED = "started"


class ComponentHealth(BaseModel):
    """Health report for a single infrastructure component."""

    name: str
    healthy: bool
    detail: str = ""


class HealthResponse(BaseModel):
    """Aggregate health-check response."""

    status: HealthStatus
    components: list[ComponentHealth] = []


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


async def _check_db(request: Request) -> ComponentHealth:
    """Ping the database and return a health component."""
    try:
        engine = request.app.state.db_engine
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return ComponentHealth(name="database", healthy=True, detail="connected")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(name="database", healthy=False, detail=str(exc))


async def _check_redis(request: Request) -> ComponentHealth:
    """Ping Redis and return a health component."""
    try:
        redis = request.app.state.redis
        await redis.ping()
        return ComponentHealth(name="redis", healthy=True, detail="connected")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(name="redis", healthy=False, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Liveness probe",
)
async def liveness() -> HealthResponse:
    """Always returns ``alive`` – the process is running."""
    return HealthResponse(status=HealthStatus.ALIVE)


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    responses={503: {"model": HealthResponse}},
)
async def readiness(request: Request) -> JSONResponse:
    """Check that the database and Redis are reachable.

    Returns **200** when all components are healthy, or **503** with
    details of which components failed.
    """
    components = [
        await _check_db(request),
        await _check_redis(request),
    ]

    all_healthy = all(c.healthy for c in components)
    health_status = HealthStatus.READY if all_healthy else HealthStatus.DEGRADED
    body = HealthResponse(status=health_status, components=components)

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )


@router.get(
    "/startup",
    response_model=HealthResponse,
    summary="Startup probe",
)
async def startup() -> HealthResponse:
    """Indicates the application has finished starting up."""
    return HealthResponse(status=HealthStatus.STARTED)
