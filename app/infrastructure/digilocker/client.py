"""Real DigiLocker HTTP API provider integration (placeholder)."""

from typing import Any

import httpx

from app.infrastructure.digilocker.interface import DigiLockerProvider
from app.schemas.provider import DigiLockerProfile, DigiLockerTokenResponse


class RealDigiLockerProvider(DigiLockerProvider):
    """Real implementation of DigiLockerProvider using an HTTP client.

    Currently a placeholder since real integrations (e.g. API Setu) are not yet implemented.
    """

    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self.http_client = http_client
        self.base_url = base_url

    async def exchange_code(self, code: str, code_verifier: str) -> DigiLockerTokenResponse:
        """Exchange code via real DigiLocker API (not implemented).

        Parameters
        ----------
        code:
            The authorization code.
        code_verifier:
            The PKCE code verifier.

        Returns
        -------
        DigiLockerTokenResponse
            The token response.
        """
        raise NotImplementedError("Real DigiLocker API integration is not implemented yet.")

    async def fetch_jwks(self) -> dict[str, Any]:
        """Fetch real JWKS keys (not implemented).

        Returns
        -------
        dict[str, Any]
            The keys.
        """
        raise NotImplementedError("Real DigiLocker JWKS integration is not implemented yet.")

    async def get_profile(self, access_token: str) -> DigiLockerProfile:
        """Fetch real user profile (not implemented).

        Parameters
        ----------
        access_token:
            The access token.

        Returns
        -------
        DigiLockerProfile
            The user profile.
        """
        raise NotImplementedError("Real DigiLocker Profile integration is not implemented yet.")
