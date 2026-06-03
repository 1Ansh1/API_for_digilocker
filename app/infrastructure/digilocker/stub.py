"""Stub DigiLocker provider implementation for offline testing."""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.infrastructure.digilocker.interface import DigiLockerProvider
from app.schemas.provider import DigiLockerProfile, DigiLockerTokenResponse


class StubDigiLockerProvider(DigiLockerProvider):
    """Canned/static response provider for DigiLocker.

    Always returns a successful token exchange and a matching profile.
    Generates a single RSA keypair on startup to sign and verify ID tokens.
    """

    def __init__(self) -> None:
        # Generate a temporary RSA keypair for token signing
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._public_key = self._private_key.public_key()
        self._kid = "stub-key-id"

        # Generate JWKS
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

        self._jwks = {"keys": [jwk]}

    async def exchange_code(self, code: str, code_verifier: str) -> DigiLockerTokenResponse:
        """Always return a valid mock token response signed with the stub key.

        Parameters
        ----------
        code:
            The authorization code.
        code_verifier:
            The PKCE code verifier.

        Returns
        -------
        DigiLockerTokenResponse
            Static success token response.
        """
        now = int(time.time())
        payload = {
            "iss": "https://api.digitallocker.gov.in",
            "sub": "stub-digilocker-id-12345",
            "aud": "stub-client-id",
            "exp": now + 3600,
            "iat": now,
            "name": "Jane Doe",
            "dob": "1995-05-15",
            "gender": "F",
        }
        headers = {"kid": self._kid}
        id_token = jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)

        return DigiLockerTokenResponse(
            access_token="stub-access-token-xyz789",
            id_token=id_token,
            expires_in=3600,
            token_type="Bearer",
            scope="read",
        )

    async def fetch_jwks(self) -> dict[str, Any]:
        """Return static JWKS containing the public key corresponding to the signed ID token.

        Returns
        -------
        dict[str, Any]
            The stub public key set.
        """
        return self._jwks

    async def get_profile(self, access_token: str) -> DigiLockerProfile:
        """Return static successful user profile details.

        Parameters
        ----------
        access_token:
            The access token.

        Returns
        -------
        DigiLockerProfile
            Static success profile.
        """
        return DigiLockerProfile(
            digilockerid="stub-digilocker-id-12345",
            name="Jane Doe",
            dob="1995-05-15",
            gender="F",
            eaadhaar="Y",
        )
