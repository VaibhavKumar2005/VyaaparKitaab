from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.cores.database import Base


class RateLimitHit(Base):
    """Shared cross-replica fixed-window rate limit counter stored in PostgreSQL."""

    __tablename__ = "rate_limit_hits"

    key: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_rate_limit_hits_window_start", "window_start"),
    )


class SseEventPayload(Base):
    """Overflow payload store for cross-replica PostgreSQL NOTIFY frames exceeding ~8 KB."""

    __tablename__ = "sse_event_payloads"

    event_id: Mapped[str] = mapped_column(String(180), primary_key=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
