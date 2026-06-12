"""Async database engine and session factory for DigiLocker Verification API.

Uses SQLAlchemy 2.0 async engine with asyncpg driver.  Engine and session
factory are created explicitly via helper functions and managed in the
application lifespan — no global singletons are created at import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as _create_async_engine,
)

if TYPE_CHECKING:
    from app.config import Settings

__all__ = ["create_async_engine", "create_session_factory"]


def create_async_engine(settings: Settings) -> AsyncEngine:
    """Build an :class:`AsyncEngine` from application settings.

    Parameters
    ----------
    settings:
        Application configuration object.  The following attributes are read:

        * ``database_url`` – async connection string (must use the
          ``mysql+aiomysql://`` scheme).
        * ``db_pool_size`` – core pool size (default handled by SQLAlchemy if
          not set on *settings*).
        * ``db_max_overflow`` – max overflow connections.
        * ``db_pool_recycle`` – connection recycle time in seconds.
        * ``debug`` – when ``True``, SQL statements are echoed to the log.

    Returns
    -------
    AsyncEngine
        A configured async engine ready for use.
    """
    return _create_async_engine(
        url=settings.db.async_url,
        echo=settings.debug,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        pool_pre_ping=True,
        connect_args={"ssl": False},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a reusable async session factory bound to *engine*.

    Sessions produced by the returned factory have ``expire_on_commit``
    disabled so that ORM objects remain usable outside the commit boundary
    without triggering lazy loads.

    Parameters
    ----------
    engine:
        The :class:`AsyncEngine` to bind sessions to.

    Returns
    -------
    async_sessionmaker[AsyncSession]
        A factory callable that yields :class:`AsyncSession` instances.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
