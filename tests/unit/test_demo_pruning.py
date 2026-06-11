"""Unit tests for demo-friendly temporary PII storage and pruning behavior."""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.models.audit_event import AuditEventType
from app.models.verification import Verification, VerificationStatus
from app.models.verification_result import VerificationResult
from app.services.verification import VerificationService


@pytest.fixture
def test_settings() -> Settings:
    """Settings instance for unit tests."""
    s = Settings(environment="testing", debug=True)
    s.demo_mode = True
    s.oauth_session.result_ttl_seconds = 300
    return s


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock database AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_audit_repo() -> MagicMock:
    """Mock AuditRepository."""
    repo = MagicMock()
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def mock_verification_repo() -> AsyncMock:
    """Mock VerificationRepository."""
    return AsyncMock()


@pytest.fixture
def mock_verification_result_repo() -> AsyncMock:
    """Mock VerificationResultRepository."""
    return AsyncMock()


@pytest.fixture
def verification_service(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
    test_settings: Settings,
    mock_audit_repo: MagicMock,
    mock_verification_repo: AsyncMock,
    mock_verification_result_repo: AsyncMock,
) -> VerificationService:
    """VerificationService instance injected with mocks."""
    from app.infrastructure.digilocker.mock import MockDigiLockerProvider
    from app.services.oauth import OAuthService
    from app.services.token import TokenService

    provider = MockDigiLockerProvider()
    jwks = AsyncMock()
    token_service = TokenService(settings=test_settings, jwks_service=jwks)
    oauth_service = OAuthService(settings=test_settings)

    return VerificationService(
        db_session=mock_db_session,
        redis=mock_redis,
        settings=test_settings,
        oauth_service=oauth_service,
        token_service=token_service,
        provider=provider,
        audit_repository=mock_audit_repo,
        verification_repository=mock_verification_repo,
        verification_result_repository=mock_verification_result_repo,
    )


@pytest.mark.asyncio
async def test_get_verification_result_fresh_demo(
    verification_service: VerificationService,
    mock_verification_result_repo: AsyncMock,
    mock_db_session: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify fresh result is returned and not pruned when demo_mode is True."""
    v_id = uuid.uuid4()
    user_id = "test-user-demo"
    
    mock_result = MagicMock(spec=VerificationResult)
    mock_result.user_id = user_id
    mock_result.name = "Alice Smith"
    mock_result.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(seconds=5)
    
    mock_verification_result_repo.get_by_verification_id = AsyncMock(return_value=mock_result)

    res = await verification_service.get_verification_result(verification_id=v_id, user_id=user_id)
    
    assert res is not None
    assert res.name == "Alice Smith"
    mock_db_session.delete.assert_not_called()
    mock_audit_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_get_verification_result_expired_demo(
    verification_service: VerificationService,
    mock_verification_result_repo: AsyncMock,
    mock_db_session: AsyncMock,
    mock_audit_repo: MagicMock,
) -> None:
    """Verify expired result is pruned on-demand (deleted and audit logged) when demo_mode is True."""
    v_id = uuid.uuid4()
    user_id = "test-user-demo"
    
    mock_result = MagicMock(spec=VerificationResult)
    mock_result.user_id = user_id
    mock_result.name = "Alice Smith"
    # Older than 15s (20s ago)
    mock_result.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(seconds=20)
    
    mock_verification_result_repo.get_by_verification_id = AsyncMock(return_value=mock_result)

    res = await verification_service.get_verification_result(verification_id=v_id, user_id=user_id)
    
    # Check that it returns None (since it has been pruned on-the-fly)
    assert res is None
    
    # Check that delete was called on db session
    mock_db_session.delete.assert_called_once_with(mock_result)
    
    # Check that PII_PRUNED audit event was logged
    mock_audit_repo.create.assert_called_once()
    call_args = mock_audit_repo.create.call_args[1]
    assert call_args["verification_id"] == v_id
    assert call_args["user_id"] == user_id
    assert call_args["event_type"] == AuditEventType.PII_PRUNED
    assert call_args["status"] == "PRUNED"
    assert call_args["metadata"]["reason"] == "retention_expired"
    assert call_args["metadata"]["retention_seconds"] == 15
    
    # Ensure no raw PII leaks into audit event metadata
    assert "name" not in call_args["metadata"]
    assert "dob" not in call_args["metadata"]
    assert "gender" not in call_args["metadata"]


@pytest.mark.asyncio
async def test_get_verification_result_expired_production(
    verification_service: VerificationService,
    mock_verification_result_repo: AsyncMock,
    mock_db_session: AsyncMock,
    mock_audit_repo: MagicMock,
    test_settings: Settings,
) -> None:
    """Verify that in production mode (demo_mode=False), the normal result_ttl_seconds applies."""
    test_settings.demo_mode = False  # Deactivate demo mode
    v_id = uuid.uuid4()
    user_id = "test-user-prod"
    
    mock_result = MagicMock(spec=VerificationResult)
    mock_result.user_id = user_id
    mock_result.name = "Alice Smith"
    
    # Case A: 20 seconds ago (Not expired for prod's 300s TTL)
    mock_result.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(seconds=20)
    mock_verification_result_repo.get_by_verification_id = AsyncMock(return_value=mock_result)
    
    res = await verification_service.get_verification_result(verification_id=v_id, user_id=user_id)
    assert res is not None
    assert res.name == "Alice Smith"
    mock_db_session.delete.assert_not_called()
    mock_audit_repo.create.assert_not_called()
    
    # Case B: 310 seconds ago (Expired for prod's 300s TTL)
    mock_result.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(seconds=310)
    res_expired = await verification_service.get_verification_result(verification_id=v_id, user_id=user_id)
    assert res_expired is None
    mock_db_session.delete.assert_called_once_with(mock_result)
    mock_audit_repo.create.assert_called_once()
    
    call_args = mock_audit_repo.create.call_args[1]
    assert call_args["metadata"]["retention_seconds"] == 300
