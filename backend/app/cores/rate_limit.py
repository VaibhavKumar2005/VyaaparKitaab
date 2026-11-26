from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import SessionLocal
from app.models.rate_limit_hit import RateLimitHit

MAX_BUCKETS = 4096
CLEANUP_INTERVAL_SECONDS = 60

_buckets: dict[str, deque[float]] = defaultdict(deque)
_last_cleanup_epoch: int = 0
_pending_db_reset: bool = False


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60) -> None:
    """
    In-memory sliding-window rate limiter with bounded bucket eviction.
    Used for local/unit-test fallbacks when no PostgreSQL AsyncSession is active.
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


async def _increment_postgres_counter(
    session: AsyncSession,
    *,
    key: str,
    window_seconds: int,
) -> int:
    global _last_cleanup_epoch, _pending_db_reset

    if _pending_db_reset:
        _pending_db_reset = False
        await session.execute(delete(RateLimitHit))

    now_epoch = int(time.time())
    win = max(1, int(window_seconds))
    window_start = (now_epoch // win) * win

    if now_epoch - _last_cleanup_epoch >= CLEANUP_INTERVAL_SECONDS:
        _last_cleanup_epoch = now_epoch
        cutoff_epoch = now_epoch - max(win * 2, 3600)
        await session.execute(
            delete(RateLimitHit).where(RateLimitHit.window_start < cutoff_epoch)
        )

    stmt = (
        pg_insert(RateLimitHit)
        .values(key=key[:255], window_start=window_start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitHit.key, RateLimitHit.window_start],
            set_={"count": RateLimitHit.count + 1},
        )
        .returning(RateLimitHit.count)
    )
    hit_count = int((await session.execute(stmt)).scalar_one())
    await session.commit()
    return hit_count


async def enforce_rate_limit(
    key: str,
    max_requests: int = 10,
    window_seconds: int = 60,
    db: Any | None = None,
) -> None:
    """
    Shared cross-replica rate limiter backed by PostgreSQL `rate_limit_hits`.
    Atomically increments `(key, window_start)` via INSERT ... ON CONFLICT DO UPDATE ... RETURNING count
    and commits immediately so failed/rejected requests still count across all replicas.
    Falls back to bounded in-memory tracking only when a non-AsyncSession mock is injected.
    """
    if db is not None and not isinstance(db, AsyncSession):
        check_rate_limit(key, max_requests=max_requests, window_seconds=window_seconds)
        return

    if isinstance(db, AsyncSession):
        hit_count = await _increment_postgres_counter(
            db, key=key, window_seconds=window_seconds
        )
    else:
        async with SessionLocal() as owned_db:
            hit_count = await _increment_postgres_counter(
                owned_db, key=key, window_seconds=window_seconds
            )

    if hit_count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


async def cleanup_expired_rate_limits(
    db: AsyncSession,
    *,
    older_than_seconds: int = 3600,
) -> int:
    """Explicitly purges expired rate_limit_hits windows and returns deleted row count."""
    cutoff_epoch = int(time.time()) - max(1, older_than_seconds)
    result = await db.execute(
        delete(RateLimitHit).where(RateLimitHit.window_start < cutoff_epoch)
    )
    await db.commit()
    return int(result.rowcount or 0)


async def reset_rate_limits_async(db: AsyncSession | None = None) -> None:
    """Clears both in-memory buckets and PostgreSQL `rate_limit_hits`."""
    global _pending_db_reset
    _buckets.clear()
    _pending_db_reset = False
    if isinstance(db, AsyncSession):
        await db.execute(delete(RateLimitHit))
        await db.commit()
    else:
        async with SessionLocal() as owned_db:
            await owned_db.execute(delete(RateLimitHit))
            await owned_db.commit()


def reset_rate_limits() -> None:
    """Clear rate limit buckets and mark PostgreSQL rate_limit_hits for reset (used in tests)."""
    global _pending_db_reset
    _buckets.clear()
    _pending_db_reset = True
