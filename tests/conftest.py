"""Shared test fixtures for DigiLocker Verification API.

Provides application-wide fixtures for the test client, settings, and
placeholder fixtures for database and Redis integration tests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings
from app.main import create_app
from app.models import Base


@pytest.fixture(scope="session")
def app_settings() -> Settings:
    """Return a Settings instance configured for testing.

    Override environment variables here to isolate tests from
    the host environment.
    """
    from app.config import ObservabilitySettings
    s = Settings(
        environment="testing",
        debug=True,
        observability=ObservabilitySettings(log_level="DEBUG"),
    )
    s.db.name = "digilocker_test"
    return s


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
# Integration test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def test_db_engine(app_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Create session-wide async database engine and setup tables."""
    engine = create_async_engine(app_settings.db.async_url, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session after truncating the tables."""
    async with test_db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE verification_results, audit_events, verifications "
                "RESTART IDENTITY CASCADE;"
            )
        )

    session = AsyncSession(bind=test_db_engine, expire_on_commit=False)
    yield session
    await session.close()


