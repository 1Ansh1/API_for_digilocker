"""Dependency injection functions for FastAPI route handlers.

These dependencies pull shared resources (DB sessions, Redis connections,
HTTP clients) from ``app.state`` which is populated during the application
lifespan.
"""

from collections.abc import AsyncGenerator

import httpx
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["get_db_session", "get_redis", "get_http_client"]


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from the app's session factory.

    The session is committed on success and rolled back on any exception so
    that callers never need to manage transactions manually.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis(request: Request) -> Redis:
    """Return the app-wide Redis connection pool."""
    return request.app.state.redis


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Return the app-wide HTTP client."""
    return request.app.state.http_client
