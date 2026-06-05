from __future__ import annotations

import contextlib
import json
import time
from typing import TYPE_CHECKING, Any

from jwt.algorithms import RSAAlgorithm

from app.errors.exceptions import IdTokenInvalidError

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.infrastructure.digilocker.interface import DigiLockerProvider

__all__ = ["JWKSService"]


class JWKSService:
    """Fetches and caches DigiLocker's JWKS public keys.

    Responsibilities:
        - Retrieve the JWKS endpoint periodically
        - Cache keys in memory / Redis with TTL-based expiry
        - Provide key lookup by ``kid`` for signature verification
    """

    def __init__(
        self,
        provider: DigiLockerProvider,
        redis: Redis,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.provider = provider
        self.redis = redis
        self.cache_ttl_seconds = cache_ttl_seconds
        self._in_memory_jwks: dict[str, Any] | None = None
        self._in_memory_expiry: float = 0.0

    async def get_public_key(self, kid: str) -> Any:
        """Retrieve the cryptography public key corresponding to the given Key ID (kid).

        Checks memory first, then Redis, and finally fetches from the provider
        on cache miss.

        Parameters
        ----------
        kid:
            The Key ID to lookup.

        Returns
        -------
        Any
            The Cryptography public key object.

        Raises
        ------
        IdTokenInvalidError
            If the key is not found in the JWKS.
        """
        now = time.time()

        # 1. Check in-memory cache
        if self._in_memory_jwks and now < self._in_memory_expiry:
            key_dict = self._find_key(self._in_memory_jwks, kid)
            if key_dict:
                return RSAAlgorithm.from_jwk(key_dict)

        # 2. Check Redis cache
        redis_key = "digilocker:jwks"
        with contextlib.suppress(Exception):
            cached_jwks_str = await self.redis.get(redis_key)
            if cached_jwks_str:
                jwks = json.loads(cached_jwks_str)
                self._in_memory_jwks = jwks
                self._in_memory_expiry = now + self.cache_ttl_seconds
                key_dict = self._find_key(jwks, kid)
                if key_dict:
                    return RSAAlgorithm.from_jwk(key_dict)

        # 3. Fetch from provider
        jwks = await self.provider.fetch_jwks()
        self._in_memory_jwks = jwks
        self._in_memory_expiry = now + self.cache_ttl_seconds

        with contextlib.suppress(Exception):
            await self.redis.set(
                redis_key,
                json.dumps(jwks),
                ex=self.cache_ttl_seconds,
            )

        key_dict = self._find_key(jwks, kid)
        if not key_dict:
            raise IdTokenInvalidError(f"Signing key with kid '{kid}' not found in JWKS.")

        return RSAAlgorithm.from_jwk(key_dict)

    def _find_key(self, jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
        """Find a key matching kid in the JWKS structure."""
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            return None
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
        return None
