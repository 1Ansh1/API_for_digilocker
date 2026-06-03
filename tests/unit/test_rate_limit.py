"""Unit tests for the Redis sliding window rate limiter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import RateLimitSettings, Settings
from app.errors.exceptions import RateLimitExceededError
from app.security.rate_limit import check_rate_limits


@pytest.mark.asyncio
async def test_rate_limit_under_limit() -> None:
    """Test that check_rate_limits passes when requests are under the threshold."""
    # Setup settings
    settings = Settings()
    settings.rate_limit = RateLimitSettings(
        user_max=5,
        user_window_seconds=3600,
        ip_max=10,
        ip_window_seconds=60,
    )

    # Mock Redis pipeline
    mock_pipeline = MagicMock()
    mock_pipeline.zremrangebyscore = MagicMock(return_value=mock_pipeline)
    mock_pipeline.zcard = MagicMock(return_value=mock_pipeline)
    mock_pipeline.zadd = MagicMock(return_value=mock_pipeline)
    mock_pipeline.expire = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(return_value=[0, 2])  # 2 existing requests

    # Mock Redis client
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    # Should execute successfully without throwing an exception
    await check_rate_limits(
        redis=mock_redis,
        settings=settings,
        user_id="test-user",
        ip_address="127.0.0.1",
    )

    # Verify pipeline was executed (2 user calls + 2 IP calls)
    assert mock_redis.pipeline.call_count == 4
    assert mock_pipeline.execute.call_count == 4


@pytest.mark.asyncio
async def test_rate_limit_user_exceeded() -> None:
    """Test that check_rate_limits raises RateLimitExceededError when user limit is exceeded."""
    settings = Settings()
    settings.rate_limit = RateLimitSettings(
        user_max=5,
        user_window_seconds=3600,
    )

    # Mock check pipeline to return current count = 5 (at limit)
    mock_check_pipeline = MagicMock()
    mock_check_pipeline.zremrangebyscore = MagicMock(return_value=mock_check_pipeline)
    mock_check_pipeline.zcard = MagicMock(return_value=mock_check_pipeline)
    mock_check_pipeline.execute = AsyncMock(return_value=[0, 5])

    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=mock_check_pipeline)
    # Mock oldest element score return (timestamp)
    mock_redis.zrange = AsyncMock(return_value=[("req-id", 1000000.0)])

    with pytest.raises(RateLimitExceededError) as exc_info:
        await check_rate_limits(
            redis=mock_redis,
            settings=settings,
            user_id="limited-user",
        )

    assert "Rate limit exceeded for user" in str(exc_info.value.message)
    assert exc_info.value.retry_after_seconds is not None
    assert exc_info.value.retry_after_seconds > 0
    # Confirm it checked but did not add the request since it failed
    assert mock_redis.pipeline.call_count == 1
    assert mock_redis.zrange.call_count == 1


@pytest.mark.asyncio
async def test_rate_limit_ip_exceeded() -> None:
    """Test that check_rate_limits raises RateLimitExceededError when IP limit is exceeded."""
    settings = Settings()
    settings.rate_limit = RateLimitSettings(
        user_max=10,
        user_window_seconds=3600,
        ip_max=5,
        ip_window_seconds=60,
    )

    # Mock pipelines for user (success) and IP (failure)
    mock_user_pipeline = MagicMock()
    mock_user_pipeline.zremrangebyscore = MagicMock(return_value=mock_user_pipeline)
    mock_user_pipeline.zcard = MagicMock(return_value=mock_user_pipeline)
    mock_user_pipeline.zadd = MagicMock(return_value=mock_user_pipeline)
    mock_user_pipeline.expire = MagicMock(return_value=mock_user_pipeline)
    mock_user_pipeline.execute = AsyncMock(return_value=[0, 2])

    mock_ip_pipeline = MagicMock()
    mock_ip_pipeline.zremrangebyscore = MagicMock(return_value=mock_ip_pipeline)
    mock_ip_pipeline.zcard = MagicMock(return_value=mock_ip_pipeline)
    mock_ip_pipeline.execute = AsyncMock(return_value=[0, 5])

    mock_redis = MagicMock()
    # Alternate pipeline calls: User check, User record, IP check
    mock_redis.pipeline = MagicMock(
        side_effect=[mock_user_pipeline, mock_user_pipeline, mock_ip_pipeline]
    )
    mock_redis.zrange = AsyncMock(return_value=[("req-id", 1000000.0)])

    with pytest.raises(RateLimitExceededError) as exc_info:
        await check_rate_limits(
            redis=mock_redis,
            settings=settings,
            user_id="test-user",
            ip_address="192.168.1.1",
        )

    assert "Rate limit exceeded for IP" in str(exc_info.value.message)
    assert exc_info.value.retry_after_seconds is not None
    assert exc_info.value.retry_after_seconds > 0
