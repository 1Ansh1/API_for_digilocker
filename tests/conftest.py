"""Shared test fixtures for DigiLocker Verification API.

Provides application-wide fixtures for the test client, settings, and
placeholder fixtures for database and Redis integration tests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Return a Settings instance configured for testing.

    Override environment variables here to isolate tests from
    the host environment.
    """
    from app.config import ObservabilitySettings
    return Settings(
        environment="testing",
        debug=True,
        observability=ObservabilitySettings(log_level="DEBUG"),
    )


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield an async HTTP client wired to the FastAPI test application.

    The client uses httpx's ASGITransport so no real network calls are made.
    """
    app = create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Integration test fixtures (placeholders)
# ---------------------------------------------------------------------------
# The fixtures below are stubs for future integration tests that will use
# testcontainers to spin up real PostgreSQL and Redis instances.
#
# Example with testcontainers:
#
#   from testcontainers.postgres import PostgresContainer
#   from testcontainers.redis import RedisContainer
#
#   @pytest.fixture(scope="session")
#   def postgres_container():
#       with PostgresContainer("postgres:16-alpine") as pg:
#           yield pg
#
#   @pytest.fixture(scope="session")
#   def redis_container():
#       with RedisContainer("redis:7-alpine") as rd:
#           yield rd
# ---------------------------------------------------------------------------
