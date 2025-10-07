"""
Retry Handler Tests
"""

import pytest
from utils.retry_handler import RetryHandler


@pytest.mark.asyncio
async def test_retry_success_first_attempt():
    """Test successful execution on first attempt"""
    handler = RetryHandler()
    
    async def success_func():
        return "success"
    
    result = await handler.retry_with_exponential_backoff(success_func)
    
    assert result == "success"


@pytest.mark.asyncio
async def test_retry_success_after_failure():
    """Test success after one failure"""
    handler = RetryHandler()
    
    call_count = 0
    
    async def fail_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("First attempt fails")
        return "success"
    
    result = await handler.retry_with_exponential_backoff(fail_once)
    
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_all_attempts_fail():
    """Test all retry attempts fail"""
    handler = RetryHandler()
    
    async def always_fails():
        raise Exception("Always fails")
    
    with pytest.raises(Exception) as exc_info:
        await handler.retry_with_exponential_backoff(always_fails, max_retries=3)
    
    assert "Always fails" in str(exc_info.value)


@pytest.mark.asyncio
async def test_retry_callback():
    """Test retry callback is called"""
    handler = RetryHandler()
    
    callback_calls = []
    
    async def on_retry(attempt, error, delay):
        callback_calls.append(attempt)
    
    call_count = 0
    
    async def fail_twice():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise Exception("Fail")
        return "success"
    
    await handler.retry_with_exponential_backoff(
        fail_twice,
        max_retries=5,
        on_retry=on_retry
    )
    
    assert len(callback_calls) == 2  # Called on first and second failure