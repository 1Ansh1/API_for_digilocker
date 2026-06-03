"""Mock DigiLocker provider implementation for offline testing and verification simulation."""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.errors.exceptions import (
    JWKSFetchError,
    ProviderUnavailableError,
    TokenExchangeError,
    UnauthorizedError,
)
from app.infrastructure.digilocker.interface import DigiLockerProvider
from app.schemas.provider import DigiLockerProfile, DigiLockerTokenResponse


class MockDigiLockerProvider(DigiLockerProvider):
    """Configurable mock provider to simulate various DigiLocker API responses.

    Supports simulated behaviors triggered by specific authorization codes
    and stateful flags for testing.
    """

    # Simulated code constants
    SUCCESS_CODE = "SUCCESS_CODE"
    EXPIRED_CODE = "EXPIRED_CODE"
    INVALID_TOKEN_CODE = "INVALID_TOKEN_CODE"
    JWKS_FAIL_CODE = "JWKS_FAIL_CODE"
    PROFILE_MISMATCH_CODE = "PROFILE_MISMATCH_CODE"
    TIMEOUT_CODE = "TIMEOUT_CODE"

    def __init__(self) -> None:
        # Generate primary key pair for valid tokens
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._public_key = self._private_key.public_key()
        self._kid = "mock-key-id-primary"

        # Generate a mismatching key pair for signature failure simulation
        self._bad_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._bad_kid = "mock-key-id-mismatch"

        # Stateful failure settings for programmatic override in tests
        self.simulate_jwks_fetch_failure = False
        self.simulate_token_exchange_timeout = False
        self.simulate_profile_fetch_timeout = False

    def _generate_jwks(self) -> dict[str, Any]:
        """Helper to generate the JWKS from the primary public key."""
        import json

        jwk = json.loads(RSAAlgorithm.to_jwk(self._public_key))
        jwk.update(
            {
                "kid": self._kid,
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
            }
        )
        return {"keys": [jwk]}


    async def exchange_code(self, code: str, code_verifier: str) -> DigiLockerTokenResponse:
        """Simulate code exchange with DigiLocker.

        Behaviors depend on the code passed:
        - SUCCESS_CODE: Returns valid token signed with the correct key.
        - EXPIRED_CODE: Raises TokenExchangeError.
        - INVALID_TOKEN_CODE: Returns an expired token response.
        - JWKS_FAIL_CODE: Returns token signed with a key not present in JWKS.
        - PROFILE_MISMATCH_CODE: Returns access token that yields mismatched profile.
        - TIMEOUT_CODE: Simulates timeout.
        """
        if self.simulate_token_exchange_timeout or code == self.TIMEOUT_CODE:
            # Simulate a timeout by raising a timeout error or ProviderUnavailableError
            raise ProviderUnavailableError("Connection timed out while exchanging code.")

        if code == self.EXPIRED_CODE:
            raise TokenExchangeError("Authorization code has expired.")

        now = int(time.time())

        # Determine payloads and signing keys based on simulated code
        if code == self.INVALID_TOKEN_CODE:
            # Token is expired or malformed
            payload = {
                "iss": "https://api.digitallocker.gov.in",
                "sub": "mock-digilocker-id-expired",
                "aud": "mock-client-id",
                "exp": now - 3600,  # expired 1 hour ago
                "iat": now - 7200,
                "name": "Expired User",
                "dob": "1980-01-01",
                "gender": "M",
            }
            headers = {"kid": self._kid}
            id_token = jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)
            access_token = "expired-access-token"

        elif code == self.JWKS_FAIL_CODE:
            # Token signed with a mismatching key that won't match JWKS
            payload = {
                "iss": "https://api.digitallocker.gov.in",
                "sub": "mock-digilocker-id-bad-sig",
                "aud": "mock-client-id",
                "exp": now + 3600,
                "iat": now,
                "name": "Bad Signature User",
                "dob": "1990-01-01",
                "gender": "M",
            }
            headers = {"kid": self._bad_kid}
            id_token = jwt.encode(
                payload,
                self._bad_private_key,
                algorithm="RS256",
                headers=headers,
            )


            access_token = "bad-sig-access-token"

        elif code == self.PROFILE_MISMATCH_CODE:
            # Happy path token, but profile retrieval will mismatch expected demographic info
            payload = {
                "iss": "https://api.digitallocker.gov.in",
                "sub": "mock-digilocker-id-mismatch",
                "aud": "mock-client-id",
                "exp": now + 3600,
                "iat": now,
                "name": "Mismatched Profile User",
                "dob": "1900-01-01",  # Mismatching date of birth
                "gender": "T",
            }
            headers = {"kid": self._kid}
            id_token = jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)
            access_token = "mismatch-access-token"

        else:
            # SUCCESS_CODE or any default code: standard happy path
            payload = {
                "iss": "https://api.digitallocker.gov.in",
                "sub": "mock-digilocker-id-success",
                "aud": "mock-client-id",
                "exp": now + 3600,
                "iat": now,
                "name": "John Doe",
                "dob": "1990-01-01",
                "gender": "M",
            }
            headers = {"kid": self._kid}
            id_token = jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)
            access_token = "valid-access-token"

        return DigiLockerTokenResponse(
            access_token=access_token,
            id_token=id_token,
            expires_in=3600,
            token_type="Bearer",
            scope="read",
        )

    async def fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS keys. Can be statefully configured to fail."""
        if self.simulate_jwks_fetch_failure:
            raise JWKSFetchError("Failed to retrieve JWKS: provider service unavailable.")

        return self._generate_jwks()

    async def get_profile(self, access_token: str) -> DigiLockerProfile:
        """Fetch user profile details using access token.

        Behaviors depend on the token value:
        - mismatch-access-token: Returns profile with mismatched name/dob.
        - expired-access-token: Raises UnauthorizedError.
        - timeout-access-token: Raises ProviderUnavailableError.
        - any other access token: Returns standard matching user profile.
        """
        if self.simulate_profile_fetch_timeout or access_token == "timeout-access-token":
            raise ProviderUnavailableError("Profile retrieval timed out.")

        if access_token == "expired-access-token":
            raise UnauthorizedError("Access token has expired or is invalid.")

        if access_token == "mismatch-access-token":
            return DigiLockerProfile(
                digilockerid="mock-digilocker-id-mismatch",
                name="Mismatched Profile User",
                dob="1900-01-01",
                gender="T",
                eaadhaar="Y",
            )

        # Standard happy path
        return DigiLockerProfile(
            digilockerid="mock-digilocker-id-success",
            name="John Doe",
            dob="1990-01-01",
            gender="M",
            eaadhaar="Y",
        )
