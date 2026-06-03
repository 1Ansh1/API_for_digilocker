"""JWT decoding and JWKS verification helpers.

Wraps the low-level JWT decode/verify operations, providing a
high-level interface that integrates with the JWKSService for
automatic key resolution.

Functions to be implemented:
    - decode_id_token: Decode and validate a DigiLocker ID token JWT.
    - verify_jwks_signature: Verify a JWT signature against a JWKS key set.
"""
