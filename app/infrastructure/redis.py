"""Redis connection pool and key-builder utilities.

Provides lifecycle functions for creating / closing a Redis connection pool
and a :class:`RedisKeyBuilder` with deterministic key-formatting helpers
for every Redis key used by the DigiLocker Verification API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = ["create_redis_pool", "close_redis_pool", "RedisKeyBuilder"]


def create_redis_pool(settings: Settings) -> aioredis.Redis:
    """Create and return a Redis connection pool.

    Parameters
    ----------
    settings:
        Application configuration.  Uses ``redis_url`` for the connection
        string and ``redis_max_connections`` (default ``20``) to cap the
        pool size.

    Returns
    -------
    redis.asyncio.Redis
        A Redis client backed by a connection pool.
    """
    return aioredis.Redis.from_url(
        url=str(settings.redis_url),
        decode_responses=True,
        max_connections=getattr(settings, "redis_max_connections", 20),
    )


async def close_redis_pool(redis: aioredis.Redis) -> None:
    """Gracefully close *redis* and release all pooled connections.

    Parameters
    ----------
    redis:
        The Redis client instance to shut down.
    """
    await redis.aclose()


class RedisKeyBuilder:
    """Deterministic key formatters for every Redis key in the system.

    All methods are static and pure — they merely format strings.
    """

    @staticmethod
    def session_key(state: str) -> str:
        """Key for an OAuth session keyed by PKCE *state* parameter."""
        return f"digilocker:session:{state}"

    @staticmethod
    def active_lock_key(user_id: str) -> str:
        """Lock key indicating an active verification for *user_id*."""
        return f"digilocker:active:{user_id}"

    @staticmethod
    def result_key(verification_id: str) -> str:
        """Key storing the verification result for *verification_id*."""
        return f"digilocker:result:{verification_id}"

    @staticmethod
    def rate_limit_user_key(user_id: str, window: str) -> str:
        """Rate-limit counter for *user_id* within *window*."""
        return f"ratelimit:user:{user_id}:{window}"

    @staticmethod
    def rate_limit_ip_key(ip: str, window: str) -> str:
        """Rate-limit counter for *ip* within *window*."""
        return f"ratelimit:ip:{ip}:{window}"

    @staticmethod
    def jwks_cache_key() -> str:
        """Key caching the DigiLocker JWKS key set."""
        return "jwks:cache"
