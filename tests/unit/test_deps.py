"""Unit tests for dependency injection functions in app/api/deps.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
import httpx

from app.api.deps import (
    get_db_session,
    get_redis,
    get_http_client,
    get_current_user_id,
    get_digilocker_provider,
    get_jwks_service,
    get_token_service,
    get_verification_service,
)
from app.errors.exceptions import UnauthorizedError
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.services.jwks import JWKSService
from app.services.token import TokenService
from app.services.verification import VerificationService


class MockState:
    """Simple class to avoid returning MagicMock for state attributes."""
    pass


@pytest.mark.asyncio
async def test_get_db_session_success() -> None:
    """Verify get_db_session commits on success."""
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Mock the async context manager returned by session_factory()
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    
    mock_factory = MagicMock(return_value=mock_context_manager)
    
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.db_session_factory = mock_factory

    generator = get_db_session(mock_request)
    session = await anext(generator)
    assert session == mock_session

    # Complete generator to trigger cleanup / commit
    try:
        await anext(generator)
    except StopAsyncIteration:
        pass

    mock_session.commit.assert_called_once()
    mock_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_get_db_session_exception() -> None:
    """Verify get_db_session rolls back on exception."""
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Mock the async context manager
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)
    
    mock_factory = MagicMock(return_value=mock_context_manager)
    
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.db_session_factory = mock_factory

    generator = get_db_session(mock_request)
    session = await anext(generator)
    assert session == mock_session

    # Raise an exception inside generator context
    with pytest.raises(ValueError):
        try:
            await generator.athrow(ValueError("Database failure"))
        except StopAsyncIteration:
            pass

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_get_redis() -> None:
    """Verify get_redis returns Redis instance from app state."""
    mock_redis = MagicMock(spec=Redis)
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.redis = mock_redis

    result = await get_redis(mock_request)
    assert result == mock_redis


@pytest.mark.asyncio
async def test_get_http_client() -> None:
    """Verify get_http_client returns HTTP client from app state."""
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.http_client = mock_client

    result = await get_http_client(mock_request)
    assert result == mock_client


def test_get_current_user_id_from_state() -> None:
    """Verify get_current_user_id retrieves from request state."""
    mock_request = MagicMock(spec=Request)
    mock_request.state = MockState()
    mock_request.state.user_id = "user-state-123"

    assert get_current_user_id(mock_request) == "user-state-123"


def test_get_current_user_id_from_headers() -> None:
    """Verify get_current_user_id falls back to X-User-Id header."""
    mock_request = MagicMock(spec=Request)
    mock_request.state = MockState()  # user_id is absent
    mock_request.headers.get.return_value = "user-header-456"

    assert get_current_user_id(mock_request) == "user-header-456"
    mock_request.headers.get.assert_called_with("x-user-id")


def test_get_current_user_id_unauthorized() -> None:
    """Verify get_current_user_id raises UnauthorizedError when missing."""
    mock_request = MagicMock(spec=Request)
    mock_request.state = MockState()  # user_id is absent
    mock_request.headers.get.return_value = None

    with pytest.raises(UnauthorizedError):
        get_current_user_id(mock_request)


def test_get_digilocker_provider_lazy_init() -> None:
    """Verify get_digilocker_provider lazily initializes the mock provider."""
    mock_request = MagicMock(spec=Request)
    delattr(mock_request.app.state, "digilocker_provider")

    provider = get_digilocker_provider(mock_request)
    assert isinstance(provider, MockDigiLockerProvider)
    assert mock_request.app.state.digilocker_provider == provider


@pytest.mark.asyncio
async def test_get_jwks_service() -> None:
    """Verify get_jwks_service constructs and returns JWKSService."""
    mock_request = MagicMock(spec=Request)
    mock_redis = MagicMock(spec=Redis)
    mock_request.app.state.digilocker_provider = MockDigiLockerProvider()

    service = await get_jwks_service(mock_request, redis=mock_redis)
    assert isinstance(service, JWKSService)
    assert service.redis == mock_redis


@pytest.mark.asyncio
async def test_get_token_service() -> None:
    """Verify get_token_service constructs and returns TokenService."""
    mock_jwks_service = MagicMock(spec=JWKSService)
    service = await get_token_service(jwks_service=mock_jwks_service)
    assert isinstance(service, TokenService)
    assert service.jwks_service == mock_jwks_service


@pytest.mark.asyncio
async def test_get_verification_service() -> None:
    """Verify get_verification_service constructs and returns VerificationService."""
    mock_request = MagicMock(spec=Request)
    mock_db = MagicMock(spec=AsyncSession)
    mock_redis = MagicMock(spec=Redis)
    mock_provider = MockDigiLockerProvider()
    mock_token_service = MagicMock(spec=TokenService)
    mock_request.app.state.digilocker_provider = mock_provider

    service = await get_verification_service(
        db_session=mock_db,
        redis=mock_redis,
        provider=mock_provider,
        token_service=mock_token_service,
    )
    assert isinstance(service, VerificationService)
    assert service.db_session == mock_db
    assert service.redis == mock_redis
    assert service.provider == mock_provider
    assert service.token_service == mock_token_service
