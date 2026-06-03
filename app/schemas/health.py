"""Health and readiness check response schemas."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Response schema for the liveness probe."""

    status: str


class ReadinessCheck(BaseModel):
    """Response schema for the readiness probe with dependency checks."""

    status: str
    checks: dict[str, str]
