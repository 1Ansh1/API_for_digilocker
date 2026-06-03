"""PKCE (Proof Key for Code Exchange) utilities.

Implements RFC 7636 code verifier and code challenge generation
for securing the OAuth 2.0 authorization code flow.
"""

import base64
import hashlib
import secrets

__all__ = ["generate_code_verifier", "generate_code_challenge"]


def generate_code_verifier() -> str:
    """Create a cryptographically random verifier string.

    Generates a high-entropy string using unreserved characters as specified in RFC 7636.
    A length of 64 bytes is used to produce an ~86 character URL-safe string.
    """
    return secrets.token_urlsafe(64)


def generate_code_challenge(code_verifier: str) -> str:
    """Derive the S256 challenge from a verifier.

    Parameters
    ----------
    code_verifier:
        The cryptographically random verifier string.

    Returns
    -------
    str
        The base64url-encoded SHA-256 hash of the verifier without padding.
    """
    sha256_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(sha256_hash).decode("ascii").rstrip("=")
    return challenge

