"""Health endpoint tests.

Verifies the liveness, readiness, and startup probes return the
expected responses.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(async_client: AsyncClient) -> None:
    """GET /health/live should always return 200 with status='alive'."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_startup(async_client: AsyncClient) -> None:
    """GET /health/startup should return 200 with status='started'."""
    response = await async_client.get("/health/startup")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
