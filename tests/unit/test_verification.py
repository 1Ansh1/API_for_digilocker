"""Unit tests for the verification session initiation service and endpoints."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import status
from httpx import AsyncClient

from app.api.deps import get_verification_service
from app.config import Settings
from app.errors.exceptions import RateLimitExceededError, VerificationAlreadyInProgressError
from app.main import create_app
from app.models.audit_event import AuditEventType
from app.models.verification import Verification, VerificationStatus
from app.repositories.audit import AuditRepository
from app.repositories.verification import VerificationRepository
from app.services.oauth import OAuthService
from app.services.verification import VerificationService


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock database AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    client = AsyncMock()
    # Mock redis.get to return None by default (no active lock)
    client.get = AsyncMock(return_value=None)
    # Mock pipeline for rate limiter
    mock_pipeline = MagicMock()
    mock_pipeline.zremrangebyscore = MagicMock(return_value=mock_pipeline)
    mock_pipeline.zcard = MagicMock(return_value=mock_pipeline)
    mock_pipeline.zadd = MagicMock(return_value=mock_pipeline)
    mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(return_value=[0, 0])
    client.pipeline = MagicMock(return_value=mock_pipeline)
    return client


@pytest.fixture
def test_settings() -> Settings:
    """Settings override for tests."""
    return Settings(
        environment="testing",
        debug=True,
    )


@pytest.fixture
def mock_verification_repo() -> AsyncMock:
    """Mock verification repository."""
    repo = AsyncMock(spec=VerificationRepository)
    # Default behavior for create
    async def mock_create(user_id: str) -> Verification:
        return Verification(
            id=uuid.uuid4(),
            user_id=user_id,
            status=VerificationStatus.INITIATED,
        )
    async def mock_update_status(
        verification_id: uuid.UUID,
        status: VerificationStatus,
    ) -> Verification:
        return Verification(
            id=verification_id,
            status=status,
        )
    repo.create = AsyncMock(side_effect=mock_create)
    repo.update_status = AsyncMock(side_effect=mock_update_status)
    return repo


@pytest.fixture
def mock_audit_repo() -> AsyncMock:
    """Mock audit repository."""
    return AsyncMock(spec=AuditRepository)


@pytest.fixture
def verification_service(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
    test_settings: Settings,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: AsyncMock,
) -> VerificationService:
    """VerificationService instance with mock dependencies."""
    oauth_service = OAuthService(test_settings)
    return VerificationService(
        db_session=mock_db_session,
        redis=mock_redis,
        settings=test_settings,
        oauth_service=oauth_service,
        audit_repository=mock_audit_repo,
        verification_repository=mock_verification_repo,
    )


# ---------------------------------------------------------------------------
# Service Layer Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_verification_success(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: AsyncMock,
) -> None:
    """Test successful verification initiation flow at service layer."""
    user_id = "test-user-id"
    redirect_uri = "https://client.app/callback"
    correlation_id = "test-correlation-id"

    # Call service
    verification_id, auth_url = await verification_service.initiate_verification(
        user_id=user_id,
        client_redirect_uri=redirect_uri,
        correlation_id=correlation_id,
    )

    # Check verification ID is returned
    assert verification_id is not None
    assert uuid.UUID(verification_id)

    # Verify authorization URL is constructed correctly
    assert "public/oauth2/1/authorize" in auth_url
    assert "response_type=code" in auth_url
    assert "redirect_uri=" in auth_url

    # Check lock checked and set
    mock_redis.get.assert_called_once()
    mock_redis.set.assert_any_call(
        f"digilocker:active:{user_id}",
        verification_id,
        ex=900,  # default lock TTL
    )

    # Verify Redis session cached with necessary OIDC fields
    # Redis session cache set should occur (keyed by state)
    called_keys = [args[0] for args, _ in mock_redis.set.call_args_list]
    state_key = [k for k in called_keys if "digilocker:session:" in k][0]
    assert state_key is not None

    # Verify cached payload structure
    session_set_call = [call for call in mock_redis.set.mock_calls if call[1][0] == state_key][0]
    session_data = json.loads(session_set_call[1][1])
    assert session_data["verification_id"] == verification_id
    assert session_data["user_id"] == user_id
    assert session_data["code_verifier"] is not None
    assert session_data["nonce"] is not None
    assert session_data["redirect_uri"] == redirect_uri

    # Check DB record creation & state transition
    mock_verification_repo.create.assert_called_once_with(user_id)
    mock_verification_repo.update_status.assert_called_once_with(
        verification_id=uuid.UUID(verification_id),
        status=VerificationStatus.REDIRECTED,
    )

    # Check Audits logged
    assert mock_audit_repo.create.call_count == 2
    # Verify first audit is INITIATED
    first_call_args = mock_audit_repo.create.call_args_list[0][1]
    assert first_call_args["event_type"] == AuditEventType.VERIFICATION_INITIATED
    assert first_call_args["status"] == VerificationStatus.INITIATED
    assert first_call_args["metadata"]["client_redirect_uri"] == redirect_uri

    # Verify second audit is REDIRECTED
    second_call_args = mock_audit_repo.create.call_args_list[1][1]
    assert second_call_args["event_type"] == AuditEventType.USER_REDIRECTED
    assert second_call_args["status"] == VerificationStatus.REDIRECTED
    assert second_call_args["metadata"]["authorization_url"] == auth_url


@pytest.mark.asyncio
async def test_initiate_verification_already_active(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
) -> None:
    """Test that initiation fails if verification lock already exists."""
    user_id = "active-user"
    # Mock redis to return an active verification ID (lock exists)
    mock_redis.get = AsyncMock(return_value="some-active-uuid")

    with pytest.raises(VerificationAlreadyInProgressError):
        await verification_service.initiate_verification(
            user_id=user_id,
            client_redirect_uri="https://client.app/callback",
            correlation_id="corr-123",
        )

    # Verify lock check was executed but flow aborted
    mock_redis.get.assert_called_once()
    mock_verification_repo.create.assert_not_called()


# ---------------------------------------------------------------------------
# API / HTTP Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_initiate_success() -> None:
    """Test API POST /initiate endpoint success path."""
    app = create_app()

    # Create mock VerificationService to override dependency
    mock_service = AsyncMock(spec=VerificationService)
    mock_service.initiate_verification = AsyncMock(
        return_value=("mocked-uuid", "http://mock-auth-url")
    )

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.post(
            "/api/v1/verification/initiate",
            json={"redirect_uri": "https://myapp.com/callback"},
            headers={"x-user-id": "api-test-user"},
        )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["verification_id"] == "mocked-uuid"
    assert data["authorization_url"] == "http://mock-auth-url"

    # Verify service method was called with correct args
    mock_service.initiate_verification.assert_called_once()
    kwargs = mock_service.initiate_verification.call_args[1]
    assert kwargs["user_id"] == "api-test-user"
    assert kwargs["client_redirect_uri"] == "https://myapp.com/callback"


@pytest.mark.asyncio
async def test_api_initiate_unauthorized() -> None:
    """Test API /initiate returns 401 when user identity is missing."""
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.post(
            "/api/v1/verification/initiate",
            json={"redirect_uri": "https://myapp.com/callback"},
            # missing X-User-Id header
        )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_api_initiate_conflict() -> None:
    """Test API returns 409 Conflict when a flow is already in progress."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.initiate_verification = AsyncMock(
        side_effect=VerificationAlreadyInProgressError("Already in progress")
    )

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.post(
            "/api/v1/verification/initiate",
            json={"redirect_uri": "https://myapp.com/callback"},
            headers={"x-user-id": "api-test-user"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data["error"]["code"] == "VERIFICATION_ALREADY_IN_PROGRESS"


@pytest.mark.asyncio
async def test_api_initiate_rate_limited() -> None:
    """Test API returns 429 Too Many Requests when rate limit is exceeded."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.initiate_verification = AsyncMock(
        side_effect=RateLimitExceededError("Rate limit exceeded", retry_after_seconds=30)
    )

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.post(
            "/api/v1/verification/initiate",
            json={"redirect_uri": "https://myapp.com/callback"},
            headers={"x-user-id": "api-test-user"},
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = response.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert data["error"]["retry_after_seconds"] == 30
