"""
Rate Limiter Tests
"""

import pytest
import asyncio
from utils.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limit_allows_requests():
    """Test rate limiter allows requests within limit"""
    limiter = RateLimiter()
    
    allowed, retry_after = limiter.check_rate_limit(
        "test_user",
        max_requests=5,
        window_seconds=60
    )
    
    assert allowed is True
    assert retry_after is None


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess():
    """Test rate limiter blocks excess requests"""
    limiter = RateLimiter()
    
    # Make 5 requests (the limit)
    for i in range(5):
        allowed, _ = limiter.check_rate_limit(
            "test_user_2",
            max_requests=5,
            window_seconds=60
        )
        assert allowed is True
    
    # 6th request should be blocked
    allowed, retry_after = limiter.check_rate_limit(
        "test_user_2",
        max_requests=5,
        window_seconds=60
    )
    
    assert allowed is False
    assert retry_after is not None
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rate_limit_window_reset():
    """Test rate limit resets after window"""
    limiter = RateLimiter()
    
    # Make max requests
    for i in range(3):
        limiter.check_rate_limit(
            "test_user_3",
            max_requests=3,
            window_seconds=1
        )
    
    # Should be blocked
    allowed, _ = limiter.check_rate_limit(
        "test_user_3",
        max_requests=3,
        window_seconds=1
    )
    assert allowed is False
    
    # Wait for window to reset
    await asyncio.sleep(1.1)
    
    # Should be allowed again
    allowed, _ = limiter.check_rate_limit(
        "test_user_3",
        max_requests=3,
        window_seconds=1
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limit_remaining_requests():
    """Test getting remaining requests"""
    limiter = RateLimiter()
    
    # Make 2 requests
    limiter.check_rate_limit("test_user_4", max_requests=5, window_seconds=60)
    limiter.check_rate_limit("test_user_4", max_requests=5, window_seconds=60)
    
    # Check remaining
    remaining = limiter.get_remaining_requests("test_user_4", max_requests=5)
    
    assert remaining == 3