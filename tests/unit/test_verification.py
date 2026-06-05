"""Unit tests for the verification session initiation service and endpoints."""

import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import status
from httpx import AsyncClient

from app.api.deps import get_verification_service
from app.config import Settings
from app.errors.exceptions import (
    IdTokenInvalidError,
    InvalidStateError,
    ProviderUnavailableError,
    RateLimitExceededError,
    SessionExpiredError,
    TokenExchangeError,
    VerificationAlreadyInProgressError,
    VerificationNotFoundError,
)
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.main import create_app
from app.models.audit_event import AuditEventType
from app.models.verification import Verification, VerificationStatus
from app.repositories.audit import AuditRepository
from app.repositories.verification import VerificationRepository
from app.repositories.verification_result import VerificationResultRepository
from app.services.jwks import JWKSService
from app.services.oauth import OAuthService
from app.services.token import TokenService
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
    return MagicMock(spec=AuditRepository)


@pytest.fixture
def mock_verification_result_repo() -> AsyncMock:
    """Mock verification result repository."""
    return AsyncMock(spec=VerificationResultRepository)


@pytest.fixture
def mock_provider() -> MockDigiLockerProvider:
    """Mock DigiLocker provider."""
    return MockDigiLockerProvider()


@pytest.fixture
def mock_jwks_service(mock_provider: MockDigiLockerProvider, mock_redis: AsyncMock) -> JWKSService:
    """JWKSService instance."""
    return JWKSService(provider=mock_provider, redis=mock_redis)


@pytest.fixture
def mock_token_service(test_settings: Settings, mock_jwks_service: JWKSService) -> TokenService:
    """TokenService instance."""
    return TokenService(settings=test_settings, jwks_service=mock_jwks_service)


@pytest.fixture
def verification_service(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
    test_settings: Settings,
    mock_provider: MockDigiLockerProvider,
    mock_token_service: TokenService,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
    mock_verification_result_repo: AsyncMock,
) -> VerificationService:
    """VerificationService instance with mock dependencies."""
    oauth_service = OAuthService(test_settings)
    return VerificationService(
        db_session=mock_db_session,
        redis=mock_redis,
        settings=test_settings,
        oauth_service=oauth_service,
        token_service=mock_token_service,
        provider=mock_provider,
        audit_repository=mock_audit_repo,
        verification_repository=mock_verification_repo,
        verification_result_repository=mock_verification_result_repo,
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


# ---------------------------------------------------------------------------
# Callback Handling & Status Query Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_callback_success(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Test callback flow success path with valid tokens, JWKS signature, and profile."""
    state = "valid-state"
    verification_id = uuid.uuid4()
    user_id = "test-user-id"
    nonce = "test-nonce-token"
    code_verifier = "test-verifier-string"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": code_verifier,
        "nonce": nonce,
        "redirect_uri": "https://my.app/callback",
    }

    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # Execute
    result = await verification_service.handle_callback(
        code=f"{MockDigiLockerProvider.SUCCESS_CODE}:{nonce}",
        state=state,
        error=None,
        error_description=None,
        correlation_id="corr-success",
    )

    # Verify status transitions
    assert result.status == VerificationStatus.VERIFIED
    assert result.digilocker_id_hash is not None
    assert result.proof_hash is not None
    assert result.completed_at is not None

    # Check cleanup
    mock_redis.delete.assert_any_call(f"digilocker:session:{state}")
    mock_redis.delete.assert_any_call(f"digilocker:active:{user_id}")

    # Check audits logged (CALLBACK_RECEIVED, TOKEN_EXCHANGE_STARTED,
    # TOKEN_EXCHANGE_COMPLETED, ID_TOKEN_VALIDATED, VERIFICATION_COMPLETED)
    assert mock_audit_repo.create.call_count >= 5


@pytest.mark.asyncio
async def test_handle_callback_missing_state(
    verification_service: VerificationService,
) -> None:
    """Verify handle_callback raises InvalidStateError if state is missing."""
    with pytest.raises(InvalidStateError):
        await verification_service.handle_callback(
            code="some_code",
            state=None,
            error=None,
            error_description=None,
            correlation_id="corr-err",
        )


@pytest.mark.asyncio
async def test_handle_callback_session_expired(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
) -> None:
    """Verify handle_callback raises SessionExpiredError if session expired in Redis."""
    mock_redis.get = AsyncMock(return_value=None)

    with pytest.raises(SessionExpiredError):
        await verification_service.handle_callback(
            code="some_code",
            state="expired-state",
            error=None,
            error_description=None,
            correlation_id="corr-err",
        )


@pytest.mark.asyncio
async def test_handle_callback_oauth_error(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify handle_callback transitions to FAILED when provider passes error."""
    state = "error-state"
    verification_id = uuid.uuid4()
    user_id = "test-user-id"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    with pytest.raises(TokenExchangeError):
        await verification_service.handle_callback(
            code=None,
            state=state,
            error="access_denied",
            error_description="User denied authorization",
            correlation_id="corr-err",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "access_denied"
    assert db_verification.error_message is not None
    assert "denied" in db_verification.error_message
    assert db_verification.completed_at is not None

    # Redis state and lock should be cleaned up
    mock_redis.delete.assert_any_call(f"digilocker:session:{state}")
    mock_redis.delete.assert_any_call(f"digilocker:active:{user_id}")

    # Check FAILED audits
    failed_audits = [
        call[1]["event_type"] for call in mock_audit_repo.create.call_args_list
    ]
    assert AuditEventType.TOKEN_EXCHANGE_FAILED in failed_audits
    assert AuditEventType.VERIFICATION_FAILED in failed_audits


@pytest.mark.asyncio
async def test_handle_callback_exchange_failed(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify handle_callback handles token exchange timeout/failure cleanly."""
    state = "timeout-state"
    verification_id = uuid.uuid4()
    user_id = "test-user"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # Exchange timeout code yields ProviderUnavailableError
    with pytest.raises(ProviderUnavailableError):
        await verification_service.handle_callback(
            code=MockDigiLockerProvider.TIMEOUT_CODE,
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-timeout",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_handle_callback_invalid_id_token_expired(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify ID token signature verification and validation failure paths (Expired Token)."""
    state = "expired-token-state"
    verification_id = uuid.uuid4()
    user_id = "test-user"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # INVALID_TOKEN_CODE returns an expired ID Token
    with pytest.raises(IdTokenInvalidError):
        await verification_service.handle_callback(
            code=MockDigiLockerProvider.INVALID_TOKEN_CODE,
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-expired",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "ID_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_handle_callback_invalid_id_token_signature(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify ID token signature verification and validation failure paths (Bad Signature)."""
    state = "bad-sig-state"
    verification_id = uuid.uuid4()
    user_id = "test-user"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # JWKS_FAIL_CODE returns a token signed with a key not present in JWKS
    with pytest.raises(IdTokenInvalidError):
        await verification_service.handle_callback(
            code=MockDigiLockerProvider.JWKS_FAIL_CODE,
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-bad-sig",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "ID_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_handle_callback_nonce_mismatch(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify ID token validation failure paths (Nonce Mismatch)."""
    state = "mismatch-nonce-state"
    verification_id = uuid.uuid4()
    user_id = "test-user"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "mismatch-nonce-value-here",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    with pytest.raises(IdTokenInvalidError) as exc_info:
        await verification_service.handle_callback(
            code=MockDigiLockerProvider.SUCCESS_CODE,
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-mismatch",
        )
    assert "nonce" in str(exc_info.value).lower()
    assert db_verification.status == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_api_callback_endpoint_success() -> None:
    """Test FastAPI callback API GET endpoint success case."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    verification_id = uuid.uuid4()
    mock_verification = Verification(
        id=verification_id,
        user_id="user-123",
        status=VerificationStatus.VERIFIED,
        completed_at=datetime.datetime.now(datetime.UTC),
        proof_hash="hash-12345",
    )
    mock_service.handle_callback = AsyncMock(return_value=mock_verification)

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get(
            "/api/v1/callback?code=SUCCESS_CODE&state=test-state"
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(verification_id)
    assert data["status"] == "VERIFIED"
    assert data["proof_hash"] == "hash-12345"


@pytest.mark.asyncio
async def test_api_callback_endpoint_failure() -> None:
    """Test FastAPI callback API GET endpoint failure propagation."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.handle_callback = AsyncMock(
        side_effect=SessionExpiredError("OAuth session expired")
    )

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/api/v1/callback?code=some_code&state=expired")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error"]["code"] == "SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_api_status_endpoint_success() -> None:
    """Test API GET /status/{verification_id} endpoint success."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    v_id = uuid.uuid4()
    completed = datetime.datetime.now(datetime.UTC)
    mock_verification = Verification(
        id=v_id,
        user_id="api-test-user",
        status=VerificationStatus.VERIFIED,
        completed_at=completed,
        proof_hash="proof-xyz",
    )
    mock_service.get_verification_status = AsyncMock(return_value=mock_verification)

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get(
            f"/api/v1/verification/status/{v_id}",
            headers={"x-user-id": "api-test-user"},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(v_id)
    assert data["status"] == "VERIFIED"
    assert data["proof_hash"] == "proof-xyz"


@pytest.mark.asyncio
async def test_api_status_endpoint_not_found() -> None:
    """Test API GET /status/{verification_id} endpoint returns 404 on missing session."""
    app = create_app()

    mock_service = AsyncMock(spec=VerificationService)
    mock_service.get_verification_status = AsyncMock(
        side_effect=VerificationNotFoundError("Verification session not found.")
    )

    app.dependency_overrides[get_verification_service] = lambda: mock_service

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get(
            f"/api/v1/verification/status/{uuid.uuid4()}",
            headers={"x-user-id": "api-test-user"},
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error"]["code"] == "VERIFICATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_handle_callback_verification_not_found(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
) -> None:
    """Verify handle_callback raises VerificationNotFoundError if DB record is missing."""
    state = "valid-state"
    verification_id = uuid.uuid4()
    
    session_payload = {
        "verification_id": str(verification_id),
        "user_id": "user-123",
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))
    mock_verification_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(VerificationNotFoundError):
        await verification_service.handle_callback(
            code="code",
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-123",
        )


@pytest.mark.asyncio
async def test_handle_callback_missing_code(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify handle_callback marks verification FAILED if code is missing."""
    state = "valid-state"
    verification_id = uuid.uuid4()
    user_id = "user-123"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": "nonce",
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))
    
    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    with pytest.raises(TokenExchangeError):
        await verification_service.handle_callback(
            code=None,
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-123",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "TOKEN_EXCHANGE_FAILED"


@pytest.mark.asyncio
async def test_handle_callback_get_profile_failure(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_provider: MockDigiLockerProvider,
) -> None:
    """Verify handle_callback marks verification FAILED if get_profile fails."""
    state = "valid-state"
    verification_id = uuid.uuid4()
    user_id = "test-user-id"
    nonce = "test-nonce-token"
    code_verifier = "test-verifier-string"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": code_verifier,
        "nonce": nonce,
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # Force profile call to fail
    mock_provider.get_profile = AsyncMock(side_effect=ProviderUnavailableError("Profile timeout")) # type: ignore[method-assign]

    with pytest.raises(ProviderUnavailableError):
        await verification_service.handle_callback(
            code=f"{MockDigiLockerProvider.SUCCESS_CODE}:{nonce}",
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-123",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_handle_callback_demographic_mismatch(
    verification_service: VerificationService,
    mock_redis: AsyncMock,
    mock_verification_repo: AsyncMock,
    mock_provider: MockDigiLockerProvider,
) -> None:
    """Verify handle_callback raises IdTokenInvalidError on demographic mismatch."""
    state = "valid-state"
    verification_id = uuid.uuid4()
    user_id = "test-user-id"
    nonce = "test-nonce"

    session_payload = {
        "verification_id": str(verification_id),
        "user_id": user_id,
        "code_verifier": "verifier",
        "nonce": nonce,
        "redirect_uri": "https://my.app/callback",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(session_payload))

    db_verification = Verification(
        id=verification_id,
        user_id=user_id,
        status=VerificationStatus.REDIRECTED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    # Force profile demographic mismatch
    from app.schemas.provider import DigiLockerProfile
    mock_provider.get_profile = AsyncMock(return_value=DigiLockerProfile(
        digilockerid="mismatch-id-xyz",
        name="John Doe",
        dob="1990-01-01",
        gender="M",
        eaadhaar="Y",
    )) # type: ignore[method-assign]

    # Use the mismatch code simulation
    with pytest.raises(IdTokenInvalidError):
        await verification_service.handle_callback(
            code=f"{MockDigiLockerProvider.PROFILE_MISMATCH_CODE}:{nonce}",
            state=state,
            error=None,
            error_description=None,
            correlation_id="corr-123",
        )

    assert db_verification.status == VerificationStatus.FAILED
    assert db_verification.error_code == "ID_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_get_verification_status_invalid_uuid(
    verification_service: VerificationService,
) -> None:
    """Verify get_verification_status raises VerificationNotFoundError on bad UUID format."""
    with pytest.raises(VerificationNotFoundError):
        await verification_service.get_verification_status(
            verification_id="not-a-uuid",
            user_id="user-123",
        )


@pytest.mark.asyncio
async def test_get_verification_status_other_user(
    verification_service: VerificationService,
    mock_verification_repo: AsyncMock,
) -> None:
    """Verify get_verification_status raises VerificationNotFoundError for unauthorized user."""
    v_id = uuid.uuid4()
    db_verification = Verification(
        id=v_id,
        user_id="user-A",
        status=VerificationStatus.INITIATED,
    )
    mock_verification_repo.get_by_id = AsyncMock(return_value=db_verification)

    with pytest.raises(VerificationNotFoundError):
        # Query status with user-B instead of user-A
        await verification_service.get_verification_status(
            verification_id=str(v_id),
            user_id="user-B",
        )


@pytest.mark.asyncio
async def test_get_verification_result_success_and_mismatch(
    verification_service: VerificationService,
    mock_verification_result_repo: AsyncMock,
) -> None:
    """Verify get_verification_result logic for matching and mismatching users."""
    v_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.user_id = "user-match"
    mock_verification_result_repo.get_by_verification_id = AsyncMock(return_value=mock_result)

    # Success: User matches
    res = await verification_service.get_verification_result(verification_id=v_id, user_id="user-match")
    assert res == mock_result

    # Failure: User mismatches
    res_mismatch = await verification_service.get_verification_result(verification_id=v_id, user_id="user-other")
    assert res_mismatch is None

    # Mising result
    mock_verification_result_repo.get_by_verification_id = AsyncMock(return_value=None)
    assert await verification_service.get_verification_result(verification_id=v_id, user_id="user-match") is None


@pytest.mark.asyncio
async def test_prune_expired_results(
    verification_service: VerificationService,
    mock_verification_result_repo: AsyncMock,
    test_settings: Settings,
) -> None:
    """Verify prune_expired_results delegates to repository with correct retention TTL."""
    test_settings.oauth_session.result_ttl_seconds = 600
    mock_verification_result_repo.prune_expired = AsyncMock(return_value=5)

    count = await verification_service.prune_expired_results()
    assert count == 5
    mock_verification_result_repo.prune_expired.assert_called_once_with(600)

