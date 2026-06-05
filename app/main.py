"""FastAPI application factory and lifespan management.

The :func:`create_app` factory wires up middleware, routers and exception
handlers and returns a fully configured :class:`FastAPI` instance.  Shared
infrastructure (database engine, Redis pool, HTTP client) is initialised
inside the async *lifespan* context manager and stored on ``app.state`` so
that dependency-injection functions in :mod:`app.api.deps` can retrieve them.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import __version__
from app.api.v1.router import api_v1_router, root_health_router
from app.config import Settings, get_settings
from app.errors.handlers import register_exception_handlers
from app.middleware.request_id import RequestIDMiddleware
from app.ui.router import ui_router

__all__ = ["create_app"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown resources.

    Resources are stored on ``app.state`` so that FastAPI dependency
    injection can access them without global singletons.
    """
    settings: Settings = get_settings()

    # -- Structured logging --------------------------------------------------
    log_level = settings.observability.log_level.upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        force=True,
    )
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.app_name,
        __version__,
        settings.environment,
    )

    # -- Database engine (reference only – no I/O until first query) ---------
    engine = create_async_engine(
        settings.db.async_url,
        echo=settings.db.echo,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    # -- Redis pool (reference only – lazy connect on first command) ---------
    redis = Redis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=True,
    )
    app.state.redis = redis

    # Clear stale JWKS cache in development/mock mode to avoid signature failures across restarts
    if settings.environment == "development" or settings.debug:
        try:
            await redis.delete("digilocker:jwks")
            logger.info("Cleared stale JWKS cache in Redis")
        except Exception as e:
            logger.warning("Failed to clear stale JWKS cache in Redis: %s", e)

    # -- HTTP client for outbound calls to DigiLocker -----------------------
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        headers={"User-Agent": f"{settings.app_name}/{__version__}"},
    )
    app.state.http_client = http_client

    logger.info("All resources initialised – application ready")

    yield  # ---- application runs here ----

    # -- Shutdown / cleanup --------------------------------------------------
    logger.info("Shutting down – releasing resources")

    await http_client.aclose()
    await redis.aclose()
    await engine.dispose()

    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return a fully configured :class:`FastAPI` application.

    Parameters
    ----------
    settings:
        Optional override; when *None* the cached :func:`get_settings` is
        used.  Passing an explicit instance is useful for testing.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=_lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # -- Middleware (outermost → innermost) ----------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # -- Static files --------------------------------------------------------
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # -- Routers -------------------------------------------------------------
    app.include_router(api_v1_router)
    app.include_router(root_health_router)
    app.include_router(ui_router)

    # -- Exception handlers --------------------------------------------------
    register_exception_handlers(app)

    return app
