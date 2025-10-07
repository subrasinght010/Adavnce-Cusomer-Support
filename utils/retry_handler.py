"""
Retry Handler - Exponential backoff and retry logic
"""

import asyncio
import random
from typing import Callable, Any, Optional
from datetime import datetime


# utils/retry_handler.py
# REPLACE the __init__ method with this:

class RetryHandler:
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0
    ):
        """
        Initialize retry handler
        
        Args:
            max_retries: Maximum retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
        """
        self.max_retries = max_retries
        self.base_delay = initial_delay  # Changed from 1
        self.max_delay = max_delay  # Changed from 60
        
    async def retry_with_exponential_backoff(
        self,
        func: Callable,
        *args,
        max_retries: Optional[int] = None,
        on_retry: Optional[Callable] = None,
        **kwargs
    ) -> Any:
        """
        Retry function with exponential backoff
        
        Args:
            func: Async function to retry
            max_retries: Maximum retry attempts (default: 3)
            on_retry: Optional callback on each retry
            *args, **kwargs: Arguments for func
        
        Returns:
            Result from func
        
        Raises:
            Last exception if all retries fail
        """
        max_retries = max_retries or self.max_retries
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    print(f"✅ Retry successful on attempt {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                if attempt == max_retries - 1:
                    # Last attempt failed
                    print(f"❌ All {max_retries} retry attempts failed")
                    raise
                
                # Calculate delay with exponential backoff + jitter
                delay = min(
                    self.base_delay * (2 ** attempt),
                    self.max_delay
                )
                # Add jitter (random 0-25% of delay)
                jitter = random.uniform(0, delay * 0.25)
                total_delay = delay + jitter
                
                print(f"⚠️ Attempt {attempt + 1} failed: {e}")
                print(f"   Retrying in {total_delay:.2f} seconds...")
                
                # Call retry callback if provided
                if on_retry:
                    try:
                        await on_retry(attempt, e, total_delay)
                    except:
                        pass
                
                await asyncio.sleep(total_delay)
        
        # Should never reach here
        raise last_exception
    
    async def retry_with_circuit_breaker(
        self,
        func: Callable,
        *args,
        service_name: str = "unknown",
        **kwargs
    ) -> Any:
        """
        Retry with circuit breaker pattern
        
        Circuit breaker prevents repeated calls to failing service
        """
        # This is a simplified version
        # For production, use library like 'pybreaker'
        
        try:
            return await self.retry_with_exponential_backoff(func, *args, **kwargs)
        except Exception as e:
            print(f"🔌 Circuit breaker: {service_name} is failing")
            # In production: open circuit, stop calling service
            raise


# Singleton instance
retry_handler = RetryHandler()