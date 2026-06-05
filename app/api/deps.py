"""Dependency injection functions for FastAPI route handlers.

These dependencies pull shared resources (DB sessions, Redis connections,
HTTP clients) from ``app.state`` which is populated during the application
lifespan.
"""

from collections.abc import AsyncGenerator
from typing import cast

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors.exceptions import UnauthorizedError
from app.infrastructure.digilocker.interface import DigiLockerProvider
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.repositories.audit import AuditRepository
from app.repositories.verification import VerificationRepository
from app.repositories.verification_result import VerificationResultRepository
from app.services.jwks import JWKSService
from app.services.oauth import OAuthService
from app.services.token import TokenService
from app.services.verification import VerificationService

__all__ = [
    "get_db_session",
    "get_redis",
    "get_http_client",
    "get_current_user_id",
    "get_verification_service",
    "get_digilocker_provider",
    "get_jwks_service",
    "get_token_service",
]


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
    return cast(Redis, request.app.state.redis)


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Return the app-wide HTTP client."""
    return cast(httpx.AsyncClient, request.app.state.http_client)


def get_current_user_id(request: Request) -> str:
    """Retrieve the user ID from the request state.

    Normally set by JWT authentication middleware.
    Falls back to checking the 'X-User-Id' header for offline / local testing.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        user_id = request.headers.get("x-user-id")
    if not user_id:
        raise UnauthorizedError("Missing or invalid authentication credentials.")
    return user_id


def get_digilocker_provider(request: Request) -> DigiLockerProvider:
    """Return the DigiLocker provider instance, lazily initialising a mock provider if not set."""
    if not hasattr(request.app.state, "digilocker_provider"):
        request.app.state.digilocker_provider = MockDigiLockerProvider()
    return cast(DigiLockerProvider, request.app.state.digilocker_provider)


async def get_jwks_service(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> JWKSService:
    """Dependency provider for JWKSService."""
    provider = get_digilocker_provider(request)
    return JWKSService(provider=provider, redis=redis)


async def get_token_service(
    jwks_service: JWKSService = Depends(get_jwks_service),
) -> TokenService:
    """Dependency provider for TokenService."""
    settings = get_settings()
    return TokenService(settings=settings, jwks_service=jwks_service)


async def get_verification_service(
    db_session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    provider: DigiLockerProvider = Depends(get_digilocker_provider),
    token_service: TokenService = Depends(get_token_service),
) -> VerificationService:
    """Dependency provider for VerificationService."""
    settings = get_settings()
    oauth_service = OAuthService(settings)
    audit_repository = AuditRepository(db_session)
    verification_repository = VerificationRepository(db_session)
    verification_result_repository = VerificationResultRepository(db_session)

    return VerificationService(
        db_session=db_session,
        redis=redis,
        settings=settings,
        oauth_service=oauth_service,
        token_service=token_service,
        provider=provider,
        audit_repository=audit_repository,
        verification_repository=verification_repository,
        verification_result_repository=verification_result_repository,
    )

