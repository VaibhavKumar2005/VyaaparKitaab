import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

MAX_BUCKETS = 4096
_buckets: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60) -> None:
    """
    In-memory sliding-window rate limiter with bounded bucket eviction.
    Raises HTTP 429 Too Many Requests when the caller exceeds max_requests within window_seconds.
    """
    now = time.monotonic()
    cutoff = now - window_seconds
    if key not in _buckets and len(_buckets) >= MAX_BUCKETS:
        expired_keys = [
            k for k, dq in _buckets.items() if not dq or dq[-1] < cutoff
        ]
        for ek in expired_keys:
            _buckets.pop(ek, None)
        if len(_buckets) >= MAX_BUCKETS:
            _buckets.pop(next(iter(_buckets)), None)
    q = _buckets[key]
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

