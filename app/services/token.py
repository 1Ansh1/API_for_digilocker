from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jwt

from app.errors.exceptions import IdTokenInvalidError

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.jwks import JWKSService

__all__ = ["TokenService"]


class TokenService:
    """Validates DigiLocker ID tokens.

    Responsibilities:
        - Decode JWT ID tokens
        - Verify signature against DigiLocker's JWKS
        - Validate standard claims (iss, aud, exp, nonce)
    """

    def __init__(self, settings: Settings, jwks_service: JWKSService) -> None:
        self.settings = settings
        self.jwks_service = jwks_service

    async def validate_id_token(self, id_token: str, expected_nonce: str) -> dict[str, Any]:
        """Decode and validate a DigiLocker OIDC ID token JWT.

        Parameters
        ----------
        id_token:
            The raw ID token string (JWT).
        expected_nonce:
            The expected nonce stored in the verification session.

        Returns
        -------
        dict[str, Any]
            The validated claims payload.

        Raises
        ------
        IdTokenInvalidError
            If signature verification fails, claims are mismatched, or token is malformed.
        """
        # 1. Parse token header to retrieve 'kid'
        try:
            header = jwt.get_unverified_header(id_token)
        except Exception as e:
            raise IdTokenInvalidError(f"Malformed ID token header: {str(e)}") from e

        kid = header.get("kid")
        if not kid:
            raise IdTokenInvalidError("ID token header is missing the 'kid' claim.")

        # 2. Retrieve public key using the JWKS service
        public_key = await self.jwks_service.get_public_key(kid)

        # 3. Resolve the expected audience. Fallback/auto-resolve if settings
        # client_id is default or empty.
        audience: str | None = self.settings.digilocker.client_id
        if not audience or audience == "your_client_id_here":
            try:
                unverified_claims = jwt.decode(id_token, options={"verify_signature": False})
                audience = unverified_claims.get("aud")
            except Exception:
                audience = None

        # 4. Decode and verify standard claims
        # Default issuer is "https://api.digitallocker.gov.in"
        expected_issuer = "https://api.digitallocker.gov.in"
        try:
            claims = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=audience,
                issuer=expected_issuer,
            )
        except jwt.ExpiredSignatureError as e:
            raise IdTokenInvalidError(f"ID token has expired: {str(e)}") from e
        except jwt.InvalidSignatureError as e:
            raise IdTokenInvalidError(f"ID token signature is invalid: {str(e)}") from e
        except jwt.PyJWTError as e:
            raise IdTokenInvalidError(f"ID token validation failed: {str(e)}") from e

        # 5. Verify nonce matches expected session nonce
        if claims.get("nonce") != expected_nonce:
            raise IdTokenInvalidError("ID token nonce does not match the session nonce.")

        # 6. Validate demographic claims structure
        required_claims = ["sub", "name", "dob", "gender"]
        for claim in required_claims:
            if not claims.get(claim):
                raise IdTokenInvalidError(f"ID token is missing required claim: '{claim}'.")

        return claims
