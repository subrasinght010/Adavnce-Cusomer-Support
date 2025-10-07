"""
Rate Limiter - Prevent abuse and DoS attacks
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta


class RateLimiter:
    def __init__(self):
        # Store request counts: {identifier: [(timestamp, count), ...]}
        self.requests: Dict[str, list] = defaultdict(list)
        self.cleanup_interval = 300  # Clean old entries every 5 minutes
        self.last_cleanup = time.time()
    
    def check_rate_limit(
        self,
        identifier: str,
        max_requests: int = 10,
        window_seconds: int = 60
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request is within rate limit
        
        Args:
            identifier: Unique identifier (IP, phone, email)
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
        
        Returns:
            Tuple of (allowed: bool, retry_after: Optional[int])
        """
        now = time.time()
        window_start = now - window_seconds
        
        # Cleanup old entries periodically
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries(window_start)
        
        # Get requests in current window
        requests_in_window = [
            ts for ts in self.requests[identifier]
            if ts > window_start
        ]
        
        # Update requests list
        self.requests[identifier] = requests_in_window
        
        # Check limit
        if len(requests_in_window) >= max_requests:
            # Calculate retry_after
            oldest_request = min(requests_in_window)
            retry_after = int(oldest_request + window_seconds - now)
            return False, max(retry_after, 1)
        
        # Add current request
        self.requests[identifier].append(now)
        return True, None
    
    def _cleanup_old_entries(self, cutoff_time: float):
        """Remove old entries to prevent memory bloat"""
        for identifier in list(self.requests.keys()):
            self.requests[identifier] = [
                ts for ts in self.requests[identifier]
                if ts > cutoff_time
            ]
            
            # Remove empty entries
            if not self.requests[identifier]:
                del self.requests[identifier]
        
        self.last_cleanup = time.time()
    
    def get_remaining_requests(
        self,
        identifier: str,
        max_requests: int = 10,
        window_seconds: int = 60
    ) -> int:
        """Get number of remaining requests in current window"""
        now = time.time()
        window_start = now - window_seconds
        
        requests_in_window = [
            ts for ts in self.requests.get(identifier, [])
            if ts > window_start
        ]
        
        return max(0, max_requests - len(requests_in_window))
    
    def reset_identifier(self, identifier: str):
        """Reset rate limit for specific identifier"""
        if identifier in self.requests:
            del self.requests[identifier]

    async def allow_request(
        self,
        identifier: str,
        max_requests: int = 60,
        window_seconds: int = 60
    ) -> bool:
        """
        Simple check if request is allowed
        
        Args:
            identifier: Unique identifier
            max_requests: Max requests per window
            window_seconds: Time window
            
        Returns:
            True if allowed, False if rate limited
        """
        allowed, retry_after = self.check_rate_limit(
            identifier,
            max_requests=max_requests,
            window_seconds=window_seconds
        )
        
        return allowed
# Singleton instance
rate_limiter = RateLimiter()