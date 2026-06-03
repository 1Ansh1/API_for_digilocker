"""Interface for DigiLocker API provider integrations."""

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.provider import DigiLockerProfile, DigiLockerTokenResponse


class DigiLockerProvider(ABC):
    """Abstract base class defining the contract for a DigiLocker provider.

    Any implementation (real, mock, stub) must implement these methods to ensure
    the system is loosely coupled and testable offline.
    """

    @abstractmethod
    async def exchange_code(self, code: str, code_verifier: str) -> DigiLockerTokenResponse:
        """Exchange an OAuth 2.0 authorization code for access and ID tokens.

        Parameters
        ----------
        code:
            The authorization code received from the callback.
        code_verifier:
            The PKCE code verifier matching the challenge sent during authorization.

        Returns
        -------
        DigiLockerTokenResponse
            Model containing access_token, id_token (JWT), and expires_in.

        Raises
        ------
        TokenExchangeError
            If exchange fails due to invalid/expired code or configuration error.
        ProviderUnavailableError
            If the DigiLocker provider is unreachable or times out.
        """
        pass

    @abstractmethod
    async def fetch_jwks(self) -> dict[str, Any]:
        """Retrieve the JSON Web Key Set (JWKS) containing DigiLocker public signing keys.

        Returns
        -------
        dict[str, Any]
            The raw JWKS dictionary mapping key IDs to public key parameters.

        Raises
        ------
        JWKSFetchError
            If fetching keys fails or the returned keys are invalid.
        ProviderUnavailableError
            If the provider is unreachable or times out.
        """
        pass

    @abstractmethod
    async def get_profile(self, access_token: str) -> DigiLockerProfile:
        """Retrieve user profile/demographic details using an active access token.

        Parameters
        ----------
        access_token:
            The active access token obtained from the token exchange.

        Returns
        -------
        DigiLockerProfile
            Model containing the user's DigiLocker ID, name, date of birth, and gender.

        Raises
        ------
        UnauthorizedError
            If the access token is invalid, expired, or revoked.
        ProviderUnavailableError
            If the provider is unreachable or times out.
        """
        pass
