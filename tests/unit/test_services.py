"""Unit tests for JWKSService, TokenService, and OAuthService."""

import json
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError

from app.config import Settings, DigiLockerSettings
from app.errors.exceptions import IdTokenInvalidError, JWKSFetchError
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.services.jwks import JWKSService
from app.services.oauth import OAuthService
from app.services.token import TokenService


@pytest.fixture
def test_settings() -> Settings:
    """Fixture returning settings configured for tests."""
    s = Settings()
    s.digilocker.client_id = "mock-client-id"
    s.digilocker.client_secret = "mock-client-secret"
    s.digilocker.base_url = "https://api.digitallocker.gov.in/"
    s.digilocker.redirect_uri = "http://localhost:8000/api/v1/callback"
    return s


@pytest.fixture
def mock_provider() -> MockDigiLockerProvider:
    """Fixture returning a mock DigiLocker provider."""
    return MockDigiLockerProvider()


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Fixture returning a mocked Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    return client


@pytest.fixture
def jwks_service(mock_provider: MockDigiLockerProvider, mock_redis: AsyncMock) -> JWKSService:
    """Fixture returning JWKSService."""
    return JWKSService(provider=mock_provider, redis=mock_redis, cache_ttl_seconds=3600)


@pytest.fixture
def token_service(test_settings: Settings, jwks_service: JWKSService) -> TokenService:
    """Fixture returning TokenService."""
    return TokenService(settings=test_settings, jwks_service=jwks_service)


@pytest.fixture
def oauth_service(test_settings: Settings) -> OAuthService:
    """Fixture returning OAuthService."""
    return OAuthService(settings=test_settings)


# ============================================================================
# OAuthService Tests
# ============================================================================

def test_oauth_build_authorization_url(oauth_service: OAuthService, test_settings: Settings) -> None:
    """Verify building of authorization URL with query parameters."""
    state = "state-123"
    code_challenge = "challenge-456"
    nonce = "nonce-789"

    url = oauth_service.build_authorization_url(state, code_challenge, nonce)
    assert "https://api.digitallocker.gov.in/public/oauth2/1/authorize" in url
    assert f"state={state}" in url
    assert f"code_challenge={code_challenge}" in url
    assert f"nonce={nonce}" in url
    assert "code_challenge_method=S256" in url
    assert f"client_id={test_settings.digilocker.client_id}" in url
    assert "redirect_uri=" in url


def test_oauth_build_authorization_url_no_trailing_slash(test_settings: Settings) -> None:
    """Verify building of authorization URL when base_url has no trailing slash."""
    test_settings.digilocker.base_url = "https://api.digitallocker.gov.in"
    oauth_service = OAuthService(settings=test_settings)
    
    url = oauth_service.build_authorization_url("state", "challenge", "nonce")
    assert "https://api.digitallocker.gov.in/public/oauth2/1/authorize" in url


# ============================================================================
# JWKSService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_jwks_service_cache_miss(
    jwks_service: JWKSService, 
    mock_provider: MockDigiLockerProvider, 
    mock_redis: AsyncMock
) -> None:
    """Verify cache miss triggers provider fetch and updates both memory and Redis."""
    # 1. Mock provider fetch_jwks spy
    mock_provider.fetch_jwks = AsyncMock(wraps=mock_provider.fetch_jwks)  # type: ignore[method-assign]
    
    kid = "mock-key-id-primary"
    key = await jwks_service.get_public_key(kid)
    assert key is not None

    # Verify provider was called
    mock_provider.fetch_jwks.assert_called_once()
    
    # Verify Redis set was called with TTL
    mock_redis.get.assert_called_once_with("digilocker:jwks")
    mock_redis.set.assert_called_once()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == "digilocker:jwks"
    assert kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_jwks_service_cache_hit_memory(
    jwks_service: JWKSService, 
    mock_provider: MockDigiLockerProvider,
    mock_redis: AsyncMock
) -> None:
    """Verify cache hit in-memory does not hit Redis or the provider."""
    # 1. Warm cache
    kid = "mock-key-id-primary"
    await jwks_service.get_public_key(kid)
    
    # 2. Reset mock calls
    mock_provider.fetch_jwks = AsyncMock(wraps=mock_provider.fetch_jwks)  # type: ignore[method-assign]
    mock_redis.get.reset_mock()
    mock_redis.set.reset_mock()

    # 3. Retrieve key again (should be cache hit in memory)
    key = await jwks_service.get_public_key(kid)
    assert key is not None

    # Assert no IO or provider calls were made
    mock_provider.fetch_jwks.assert_not_called()
    mock_redis.get.assert_not_called()
    mock_redis.set.assert_not_called()


@pytest.mark.asyncio
async def test_jwks_service_cache_hit_redis(
    jwks_service: JWKSService,
    mock_provider: MockDigiLockerProvider,
    mock_redis: AsyncMock
) -> None:
    """Verify cache hit in Redis is used when memory cache is empty/expired."""
    kid = "mock-key-id-primary"
    jwks = mock_provider._generate_jwks()
    
    # Pre-populate Redis
    mock_redis.get = AsyncMock(return_value=json.dumps(jwks))
    mock_provider.fetch_jwks = AsyncMock(wraps=mock_provider.fetch_jwks)  # type: ignore[method-assign]

    # Retrieve key
    key = await jwks_service.get_public_key(kid)
    assert key is not None

    # Assert it was loaded from Redis, not provider
    mock_redis.get.assert_called_once_with("digilocker:jwks")
    mock_provider.fetch_jwks.assert_not_called()


@pytest.mark.asyncio
async def test_jwks_service_key_not_found(jwks_service: JWKSService) -> None:
    """Verify IdTokenInvalidError is raised when kid is not found in JWKS."""
    with pytest.raises(IdTokenInvalidError) as exc_info:
        await jwks_service.get_public_key("non-existent-kid")
    assert "not found in JWKS" in str(exc_info.value)


@pytest.mark.asyncio
async def test_jwks_service_redis_failure_resilience(
    jwks_service: JWKSService, 
    mock_provider: MockDigiLockerProvider,
    mock_redis: AsyncMock
) -> None:
    """Verify that Redis errors are suppressed and keys are fetched from provider."""
    mock_redis.get = AsyncMock(side_effect=Exception("Redis connection error"))
    mock_redis.set = AsyncMock(side_effect=Exception("Redis write error"))
    mock_provider.fetch_jwks = AsyncMock(wraps=mock_provider.fetch_jwks)  # type: ignore[method-assign]

    kid = "mock-key-id-primary"
    key = await jwks_service.get_public_key(kid)
    assert key is not None
    
    # Provider must have been called successfully because redis errors were bypassed
    mock_provider.fetch_jwks.assert_called_once()


# ============================================================================
# TokenService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_token_validation_success(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation passes for a valid ID token."""
    nonce = "nonce-value-123"
    token_resp = await mock_provider.exchange_code(f"SUCCESS_CODE:{nonce}", "verifier")
    
    claims = await token_service.validate_id_token(token_resp.id_token, nonce)
    assert claims["sub"] == "mock-digilocker-id-success"
    assert claims["name"] == "John Doe"
    assert claims["dob"] == "1990-01-01"
    assert claims["gender"] == "M"
    assert claims["nonce"] == nonce


@pytest.mark.asyncio
async def test_token_validation_malformed_header(token_service: TokenService) -> None:
    """Verify validation raises IdTokenInvalidError on malformed JWT header."""
    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token("malformed.jwt.token", "nonce")
    assert "malformed id token header" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_token_validation_missing_kid(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation raises IdTokenInvalidError when kid is missing from header."""
    # Generate token without kid header
    payload = {
        "iss": "https://api.digitallocker.gov.in",
        "sub": "mock-digilocker-id-success",
        "aud": "mock-client-id",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "nonce": "nonce",
    }
    id_token = jwt.encode(payload, mock_provider._private_key, algorithm="RS256")
    
    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(id_token, "nonce")
    assert "missing the 'kid' claim" in str(exc_info.value)


@pytest.mark.asyncio
async def test_token_validation_invalid_signature(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation raises IdTokenInvalidError when signature is invalid."""
    nonce = "nonce"
    
    # Scenario A: Kid not in JWKS
    token_resp = await mock_provider.exchange_code(f"JWKS_FAIL_CODE:{nonce}", "verifier")
    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(token_resp.id_token, nonce)
    assert "not found in jwks" in str(exc_info.value).lower()

    # Scenario B: Kid is in JWKS, but signed with a different private key
    payload = {
        "iss": "https://api.digitallocker.gov.in",
        "sub": "mock-digilocker-id-success",
        "aud": "mock-client-id",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "nonce": nonce,
        "name": "John Doe",
        "dob": "1990-01-01",
        "gender": "M",
    }
    headers = {"kid": mock_provider._kid}
    bad_sig_token = jwt.encode(payload, mock_provider._bad_private_key, algorithm="RS256", headers=headers)
    
    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(bad_sig_token, nonce)
    assert "signature is invalid" in str(exc_info.value).lower()



@pytest.mark.asyncio
async def test_token_validation_expired(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation raises IdTokenInvalidError when token has expired."""
    nonce = "nonce"
    token_resp = await mock_provider.exchange_code(f"INVALID_TOKEN_CODE:{nonce}", "verifier")

    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(token_resp.id_token, nonce)
    assert "expired" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_token_validation_nonce_mismatch(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation raises IdTokenInvalidError when nonce mismatches."""
    nonce = "nonce"
    token_resp = await mock_provider.exchange_code(f"SUCCESS_CODE:{nonce}", "verifier")

    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(token_resp.id_token, "different-nonce")
    assert "nonce does not match" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_token_validation_missing_demographic_claim(
    token_service: TokenService, 
    mock_provider: MockDigiLockerProvider
) -> None:
    """Verify validation raises IdTokenInvalidError when any required claim is missing."""
    # Generate token missing "dob"
    payload = {
        "iss": "https://api.digitallocker.gov.in",
        "sub": "mock-digilocker-id-success",
        "aud": "mock-client-id",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "nonce": "nonce",
        "name": "Jane",
        # missing dob
        "gender": "F",
    }
    headers = {"kid": mock_provider._kid}
    id_token = jwt.encode(payload, mock_provider._private_key, algorithm="RS256", headers=headers)

    with pytest.raises(IdTokenInvalidError) as exc_info:
        await token_service.validate_id_token(id_token, "nonce")
    assert "missing required claim: 'dob'" in str(exc_info.value)
