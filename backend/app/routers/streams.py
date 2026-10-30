"""
Server-Sent Events (SSE) Streaming Endpoints for Live Payments & Order Updates.

Endpoints:
- GET /api/v1/streams/payments: Customer stream (scoped to current customer's payments and orders).
- GET /api/v1/streams/store/{store_id}: Store owner stream (scoped to store owned by the caller).

Security & Compliance:
- Authenticated strictly via Authorization Bearer JWT (no query string token leakage).
- Strict multi-tenant scope isolation.
- Automatic 15-second heartbeat comment (: heartbeat) to keep connection alive.
- Last-Event-ID header support for seamless client reconnect without missing transactions.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.business import Business
from app.models.user import User
from app.services.auth import get_current_user
from app.services.event_bus import subscribe_events

router = APIRouter(prefix="/streams", tags=["streams"])


async def _sse_stream_generator(
    store_id: str | None = None,
    customer_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[str]:
    """
    Consumes events from the event bus and yields SSE formatted text chunks.
    Sends `: heartbeat\n\n` comments every 15 seconds during idle periods.
    """
    try:
        async for evt in subscribe_events(
            store_id=store_id,
            customer_id=customer_id,
            last_event_id=last_event_id,
        ):
            if evt.event == ":heartbeat":
                yield ": heartbeat\n\n"
            else:
                payload = json.dumps(evt.data)
                yield f"id: {evt.id}\nevent: {evt.event}\ndata: {payload}\n\n"
    except asyncio.CancelledError:
        # Client disconnected cleanly
        pass


@router.get("/payments")
async def stream_customer_payments(
    request: Request,
    user: User = Depends(get_current_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """
    SSE stream for customers to receive real-time updates for their own payments and orders.
    Enforces customer scope isolation: only events matching the authenticated customer's ID are delivered.
    """
    # Reject token in query parameters (prevent token leakage in server logs / browser history)
    if "token" in request.query_params or "access_token" in request.query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication via query parameters is not permitted. Use the Authorization header.",
        )

    resolved_last_id = last_event_id or request.headers.get("last-event-id")

    return StreamingResponse(
        _sse_stream_generator(
            customer_id=str(user.id),
            last_event_id=resolved_last_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/store/{store_id}")
async def stream_store_payments(
    store_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """
    SSE stream for store owners to receive live incoming transaction events for their store.
    Enforces ownership check: returns 403 Forbidden if the authenticated user does not own this store.
    """
    if "token" in request.query_params or "access_token" in request.query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication via query parameters is not permitted. Use the Authorization header.",
        )

    # Verify store ownership
    res = await db.execute(
        select(Business).where(Business.id == store_id, Business.owner_id == user.id)
    )
    business = res.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this store's real-time payment stream.",
        )

    resolved_last_id = last_event_id or request.headers.get("last-event-id")

    return StreamingResponse(
        _sse_stream_generator(
            store_id=str(store_id),
            last_event_id=resolved_last_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
