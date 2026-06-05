"""Unit tests for the DigiLocker provider interfaces, stub, and mock implementations."""

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError

from app.errors.exceptions import (
    JWKSFetchError,
    ProviderUnavailableError,
    TokenExchangeError,
    UnauthorizedError,
)
from app.infrastructure.digilocker.mock import MockDigiLockerProvider
from app.infrastructure.digilocker.stub import StubDigiLockerProvider


@pytest.mark.asyncio
async def test_stub_provider() -> None:
    """Test that the Stub provider returns hardcoded successful responses and signs tokens."""
    provider = StubDigiLockerProvider()

    # 1. Exchange code
    token_resp = await provider.exchange_code("any_code", "any_verifier")
    assert token_resp.access_token == "stub-access-token-xyz789"
    assert token_resp.expires_in == 3600
    assert token_resp.token_type == "Bearer"
    assert token_resp.id_token is not None

    # 2. Fetch JWKS
    jwks = await provider.fetch_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0]["kid"] == "stub-key-id"

    # 3. Verify JWT signature with JWKS
    header = jwt.get_unverified_header(token_resp.id_token)
    assert header["kid"] == "stub-key-id"

    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])
    payload = jwt.decode(
        token_resp.id_token,
        public_key,  # type: ignore[arg-type]
        algorithms=["RS256"],
        audience="stub-client-id",
    )
    assert payload["name"] == "Jane Doe"
    assert payload["dob"] == "1995-05-15"
    assert payload["gender"] == "F"

    # 4. Get Profile
    profile = await provider.get_profile(token_resp.access_token)
    assert profile.digilockerid == "stub-digilocker-id-12345"
    assert profile.name == "Jane Doe"
    assert profile.dob == "1995-05-15"
    assert profile.gender == "F"
    assert profile.eaadhaar == "Y"


@pytest.mark.asyncio
async def test_mock_provider_success() -> None:
    """Test standard happy path for Mock provider."""
    provider = MockDigiLockerProvider()

    # Exchange success code
    token_resp = await provider.exchange_code(MockDigiLockerProvider.SUCCESS_CODE, "verifier")
    assert token_resp.access_token == "valid-access-token"
    assert token_resp.expires_in == 3600

    # Retrieve JWKS and verify signature
    jwks = await provider.fetch_jwks()
    header = jwt.get_unverified_header(token_resp.id_token)
    assert header["kid"] == "mock-key-id-primary"

    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])
    payload = jwt.decode(
        token_resp.id_token,
        public_key,  # type: ignore[arg-type]
        algorithms=["RS256"],
        audience="mock-client-id",
    )
    assert payload["name"] == "John Doe"
    assert payload["dob"] == "1990-01-01"

    # Fetch profile
    profile = await provider.get_profile(token_resp.access_token)
    assert profile.digilockerid == "mock-digilocker-id-success"
    assert profile.name == "John Doe"
    assert profile.dob == "1990-01-01"


@pytest.mark.asyncio
async def test_mock_provider_expired_code() -> None:
    """Test expired code simulation."""
    provider = MockDigiLockerProvider()

    with pytest.raises(TokenExchangeError) as exc_info:
        await provider.exchange_code(MockDigiLockerProvider.EXPIRED_CODE, "verifier")
    assert "expired" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_mock_provider_invalid_token() -> None:
    """Test invalid token simulation (expired token)."""
    provider = MockDigiLockerProvider()

    token_resp = await provider.exchange_code(MockDigiLockerProvider.INVALID_TOKEN_CODE, "verifier")
    assert token_resp.access_token == "expired-access-token"

    jwks = await provider.fetch_jwks()
    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])

    # Decoding should fail because the expiration claim is in the past
    with pytest.raises(ExpiredSignatureError):
        jwt.decode(
            token_resp.id_token,
            public_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            audience="mock-client-id",
        )

    # Calling profile with expired access token should raise UnauthorizedError
    with pytest.raises(UnauthorizedError) as exc_info:
        await provider.get_profile(token_resp.access_token)
    assert "expired" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_mock_provider_jwks_signature_failure() -> None:
    """Test signature verification failure using JWKS_FAIL_CODE."""
    provider = MockDigiLockerProvider()

    token_resp = await provider.exchange_code(MockDigiLockerProvider.JWKS_FAIL_CODE, "verifier")
    assert token_resp.access_token == "bad-sig-access-token"

    # Get primary JWKS public keys
    jwks = await provider.fetch_jwks()
    public_key = RSAAlgorithm.from_jwk(jwks["keys"][0])

    # Decode should fail because the token is signed with a different key
    with pytest.raises(InvalidSignatureError):
        jwt.decode(
            token_resp.id_token,
            public_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            audience="mock-client-id",
        )


@pytest.mark.asyncio
async def test_mock_provider_jwks_fetch_failure() -> None:
    """Test stateful simulation of JWKS fetch failure."""
    provider = MockDigiLockerProvider()
    provider.simulate_jwks_fetch_failure = True

    with pytest.raises(JWKSFetchError) as exc_info:
        await provider.fetch_jwks()
    assert "retrieve jwks" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_mock_provider_profile_mismatch() -> None:
    """Test profile mismatch simulation."""
    provider = MockDigiLockerProvider()

    token_resp = await provider.exchange_code(
        MockDigiLockerProvider.PROFILE_MISMATCH_CODE,
        "verifier",
    )
    assert token_resp.access_token == "mismatch-access-token"

    profile = await provider.get_profile(token_resp.access_token)
    assert profile.digilockerid == "mock-digilocker-id-mismatch-different"
    assert profile.name == "Mismatched Profile User"
    assert profile.dob == "1900-01-01"


@pytest.mark.asyncio
async def test_mock_provider_timeouts() -> None:
    """Test timeout simulations during exchange and profile fetch."""
    provider = MockDigiLockerProvider()

    # 1. Exchange timeout via code
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.exchange_code(MockDigiLockerProvider.TIMEOUT_CODE, "verifier")
    assert "timed out" in str(exc_info.value).lower()

    # 2. Exchange timeout via state
    provider.simulate_token_exchange_timeout = True
    with pytest.raises(ProviderUnavailableError):
        await provider.exchange_code(MockDigiLockerProvider.SUCCESS_CODE, "verifier")
    provider.simulate_token_exchange_timeout = False

    # 3. Profile timeout via access token
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.get_profile("timeout-access-token")
    assert "timed out" in str(exc_info.value).lower()

    # 4. Profile timeout via state
    provider.simulate_profile_fetch_timeout = True
    with pytest.raises(ProviderUnavailableError):
        await provider.get_profile("valid-access-token")


@pytest.mark.asyncio
async def test_real_provider_not_implemented() -> None:
    """Verify that RealDigiLockerProvider raises NotImplementedError for all interface methods."""
    import httpx
    from app.infrastructure.digilocker.client import RealDigiLockerProvider

    async with httpx.AsyncClient() as client:
        provider = RealDigiLockerProvider(client, "https://api.digitallocker.gov.in")

        with pytest.raises(NotImplementedError):
            await provider.exchange_code("code", "verifier")

        with pytest.raises(NotImplementedError):
            await provider.fetch_jwks()

        with pytest.raises(NotImplementedError):
            await provider.get_profile("token")

