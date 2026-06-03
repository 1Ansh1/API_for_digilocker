"""Redis sliding-window rate limiting utility.

Enforces per-user and per-IP rate limits using a Redis-backed
sliding window counter (sorted set) to protect against abuse and DoS.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.errors.exceptions import RateLimitExceededError
from app.infrastructure.redis import RedisKeyBuilder

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.config import Settings

__all__ = ["check_rate_limits"]


async def check_rate_limits(
    redis: Redis,
    settings: Settings,
    user_id: str,
    ip_address: str | None = None,
) -> None:
    """Check user and IP rate limits using Redis sliding window sorted sets.

    If any limit is exceeded, raises ``RateLimitExceededError``.
    Otherwise, records the request timestamp.

    Parameters
    ----------
    redis:
        Active Redis client.
    settings:
        Application configuration settings.
    user_id:
        Identifier of the calling user.
    ip_address:
        IP address of the client request.
    """
    now = time.time()

    # 1. Check/Increment User Rate Limit
    user_max = settings.rate_limit.user_max
    user_window = settings.rate_limit.user_window_seconds
    user_key = RedisKeyBuilder.rate_limit_user_key(user_id, "sliding")

    # Clean old requests and fetch current count
    pipe = redis.pipeline()
    pipe.zremrangebyscore(user_key, 0, now - user_window)
    pipe.zcard(user_key)
    _, current_user_count = await pipe.execute()

    if current_user_count >= user_max:
        # Calculate retry after based on the oldest element in the window
        oldest = await redis.zrange(user_key, 0, 0, withscores=True)
        retry_after = 1
        if oldest:
            oldest_ts = oldest[0][1]
            retry_after = max(1, int(oldest_ts + user_window - now))
        msg = f"Rate limit exceeded for user. Max {user_max} requests per {user_window} seconds."
        raise RateLimitExceededError(
            message=msg,
            retry_after_seconds=retry_after,
        )

    # Record user request
    # Use f"{now}" as member to guarantee uniqueness in sorted set
    member = f"{now}"
    pipe = redis.pipeline()
    pipe.zadd(user_key, {member: now})
    pipe.expire(user_key, user_window)
    await pipe.execute()

    # 2. Check/Increment IP Rate Limit (if IP is provided)
    if ip_address:
        ip_max = settings.rate_limit.ip_max
        ip_window = settings.rate_limit.ip_window_seconds
        ip_key = RedisKeyBuilder.rate_limit_ip_key(ip_address, "sliding")

        pipe = redis.pipeline()
        pipe.zremrangebyscore(ip_key, 0, now - ip_window)
        pipe.zcard(ip_key)
        _, current_ip_count = await pipe.execute()

        if current_ip_count >= ip_max:
            oldest = await redis.zrange(ip_key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                oldest_ts = oldest[0][1]
                retry_after = max(1, int(oldest_ts + ip_window - now))
            msg = f"Rate limit exceeded for IP. Max {ip_max} requests per {ip_window} seconds."
            raise RateLimitExceededError(
                message=msg,
                retry_after_seconds=retry_after,
            )

        pipe = redis.pipeline()
        pipe.zadd(ip_key, {f"{now}": now})
        pipe.expire(ip_key, ip_window)
        await pipe.execute()
