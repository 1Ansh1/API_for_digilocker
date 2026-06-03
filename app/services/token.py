"""DigiLocker ID token validation service.

Decodes and validates the ID token returned by DigiLocker after a
successful OAuth exchange, verifying signature, audience, issuer,
and expiry claims.
"""


class TokenService:
    """Validates DigiLocker ID tokens.

    Responsibilities:
        - Decode JWT ID tokens
        - Verify signature against DigiLocker's JWKS
        - Validate standard claims (iss, aud, exp, nonce)
    """

    pass
