"""Cryptographic state and nonce generation.

Provides functions for generating cryptographically secure random
values used as OAuth ``state`` parameters and OpenID Connect nonces
to prevent CSRF and replay attacks.
"""

import secrets

__all__ = ["generate_state", "generate_nonce"]


def generate_state() -> str:
    """Create a URL-safe random state token.

    Generates a 32-byte cryptographically secure random token (43 characters).
    """
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Create a random nonce for ID token binding.

    Generates a 32-byte cryptographically secure random token (43 characters).
    """
    return secrets.token_urlsafe(32)

