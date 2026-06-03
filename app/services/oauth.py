"""OAuth 2.0 + PKCE integration with DigiLocker.

Handles authorization URL construction, authorization-code exchange,
and token refresh using the PKCE extension for public clients.
"""

from urllib.parse import urlencode

from app.config import Settings

__all__ = ["OAuthService"]


class OAuthService:
    """Handles OAuth 2.0 + PKCE flow with DigiLocker.

    Responsibilities:
        - Build the authorization redirect URL with PKCE challenge
        - Exchange authorization codes for access/ID tokens
        - Manage token lifecycle (refresh, revocation)
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        nonce: str,
    ) -> str:
        """Build the redirect URL to DigiLocker's authorization endpoint.

        Parameters
        ----------
        state:
            Random state token for CSRF protection.
        code_challenge:
            PKCE S256 challenge string.
        nonce:
            Replay protection nonce.

        Returns
        -------
        str
            The formatted authorization redirect URL with all parameters encoded.
        """
        base_url = self.settings.digilocker.base_url
        if base_url.endswith("/"):
            auth_url = f"{base_url}public/oauth2/1/authorize"
        else:
            auth_url = f"{base_url}/public/oauth2/1/authorize"

        params = {
            "response_type": "code",
            "client_id": self.settings.digilocker.client_id,
            "redirect_uri": self.settings.digilocker.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "nonce": nonce,
        }
        return f"{auth_url}?{urlencode(params)}"

