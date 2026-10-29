import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

_buckets: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60) -> None:
    """
    In-memory sliding-window rate limiter for authentication and OTP endpoints.
    Raises HTTP 429 Too Many Requests when the caller exceeds max_requests within window_seconds.
    """
    now = time.monotonic()
    q = _buckets[key]
    cutoff = now - window_seconds
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    q.append(now)


def reset_rate_limits() -> None:
    """Clear rate limit buckets (used in automated tests)."""
    _buckets.clear()

