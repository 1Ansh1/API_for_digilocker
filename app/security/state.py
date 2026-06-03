"""Cryptographic state and nonce generation.

Provides functions for generating cryptographically secure random
values used as OAuth ``state`` parameters and OpenID Connect nonces
to prevent CSRF and replay attacks.

Functions to be implemented:
    - generate_state: Create a URL-safe random state token.
    - generate_nonce: Create a random nonce for ID token binding.
"""
