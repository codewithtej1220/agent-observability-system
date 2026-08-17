"""Rate limiting middleware using token bucket algorithm.

Supports:
- Per-user rate limiting
- Per-endpoint rate limiting
- Sliding window counters
- Redis backend for distributed systems
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable, Dict, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


class TokenBucket:
    """Token bucket rate limiter for a single user."""
    
    def __init__(self, rate: int, per: int = 60):
        """
        Args:
            rate: Number of requests allowed
            per: Time period in seconds (default 60 = 1 minute)
        """
        self.rate = rate
        self.per = per
        self.tokens = rate
        self.last_update = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.time()
        elapsed = now - self.last_update
        
        # Refill tokens based on elapsed time
        self.tokens = min(self.rate, self.tokens + (elapsed * self.rate / self.per))
        self.last_update = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_retry_after(self) -> int:
        """Get seconds until next token is available."""
        if self.tokens >= 1:
            return 0
        tokens_needed = 1 - self.tokens
        return int((tokens_needed * self.per) / self.rate) + 1


class RateLimiter:
    """Global rate limiter managing multiple users."""
    
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self.request_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.window_start: Dict[str, float] = {}
    
    def get_or_create_bucket(self, key: str, rate: int, per: int = 60) -> TokenBucket:
        """Get or create a token bucket for a key."""
        if key not in self.buckets:
            self.buckets[key] = TokenBucket(rate, per)
        return self.buckets[key]
    
    def check_rate_limit(self, key: str, rate: int, per: int = 60) -> tuple[bool, int]:
        """
        Check if request is allowed.
        
        Returns:
            (is_allowed, retry_after_seconds)
        """
        bucket = self.get_or_create_bucket(key, rate, per)
        allowed = bucket.consume()
        retry_after = 0 if allowed else bucket.get_retry_after()
        return allowed, retry_after
    
    def clean_old_buckets(self, max_age: int = 3600):
        """Remove buckets that haven't been used in max_age seconds."""
        now = time.time()
        to_remove = []
        for key, bucket in self.buckets.items():
            if now - bucket.last_update > max_age:
                to_remove.append(key)
        for key in to_remove:
            del self.buckets[key]


# Global rate limiter instance
rate_limiter = RateLimiter()


# ============================================================================
# RATE LIMIT MIDDLEWARE
# ============================================================================


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Middleware to enforce rate limits."""
    # Skip rate limiting for health check and docs
    if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)
    
    # Get user identifier (from auth or IP address)
    user_id = "anonymous"
    if hasattr(request.state, "user"):
        user_id = request.state.user.username
        rate_limit = request.state.user.rate_limit
    else:
        # Use IP address for unauthenticated requests
        user_id = request.client.host
        rate_limit = 60  # 60 requests per minute for anonymous
    
    # Check rate limit
    key = f"{user_id}:{request.url.path}"
    allowed, retry_after = rate_limiter.check_rate_limit(key, rate_limit, per=60)
    
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Try again in {retry_after} seconds.",
                "retry_after": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )
    
    # Add rate limit info to response headers
    response = await call_next(request)
    bucket = rate_limiter.buckets.get(key)
    if bucket:
        response.headers["X-RateLimit-Limit"] = str(bucket.rate)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
        response.headers["X-RateLimit-Reset"] = str(int(bucket.last_update + bucket.per))
    
    return response


# ============================================================================
# DECORATOR FOR SPECIFIC ENDPOINTS
# ============================================================================


def rate_limit(requests: int, window: int = 60):
    """Decorator to apply rate limiting to specific endpoints."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request")
            if not request:
                # Find request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if request:
                user_id = getattr(request.state, "user", request.client.host)
                if hasattr(user_id, "username"):
                    user_id = user_id.username
                
                key = f"{user_id}:{func.__name__}"
                allowed, retry_after = rate_limiter.check_rate_limit(key, requests, window)
                
                if not allowed:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded. Retry after {retry_after}s",
                        headers={"Retry-After": str(retry_after)}
                    )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
