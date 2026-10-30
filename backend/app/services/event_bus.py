"""
Event Bus Service for Real-Time Streaming (SSE / WebSockets).

Architecture & Transport Choice:
---------------------------------
In a horizontally scaled, multi-instance deployment behind a reverse proxy (e.g. NGINX
or Azure Container Apps), individual application processes do not share memory. An incoming
webhook processed by Worker Node A must publish an event that reaches a long-lived SSE stream
connected to Worker Node B.

To accommodate this architecture, message delivery is placed behind the `EventTransport`
protocol. The default implementation, `InMemoryEventBus`, uses per-subscriber `asyncio.Queue`
instances with an in-memory replay buffer for the single-instance case, local development,
and integration testing. For multi-instance deployments, an implementation backed by
PostgreSQL's native `LISTEN` / `NOTIFY` (using `asyncpg.connection.add_listener`) or Redis
Pub/Sub can be configured as the active transport without modifying route handlers,
authentication scopes, or frontend SSE listeners.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass
class StreamEvent:
    id: str
    event: str
    data: dict[str, Any]
    store_id: str | None = None
    customer_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def matches_scope(self, store_id: str | None, customer_id: str | None) -> bool:
        """
        Enforces strict multi-tenant scope isolation:
        - If a subscriber is scoped to a store_id, they only receive events for that store.
        - If a subscriber is scoped to a customer_id, they only receive events for that customer.
        - Global/internal subscribers receive all events.
        """
        if store_id is not None:
            return self.store_id == str(store_id)
        if customer_id is not None:
            return self.customer_id == str(customer_id)
        return True


class EventTransport(Protocol):
    """
    Interface for event bus transports. Enables dropping in PostgreSQL LISTEN/NOTIFY
    or Redis Pub/Sub for multi-instance deployments.
    """

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        store_id: str | None = None,
        customer_id: str | None = None,
        event_id: str | None = None,
    ) -> StreamEvent: ...

    async def subscribe(
        self,
        store_id: str | None = None,
        customer_id: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


class InMemoryEventBus:
    """
    Single-instance in-process event bus using asyncio.Queue per subscriber
    and a bounded ring buffer for Last-Event-ID reconnection replay.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._counter: int = 0
        self._history: deque[StreamEvent] = deque(maxlen=max_history)
        self._subscribers: dict[
            str, tuple[asyncio.Queue[StreamEvent], str | None, str | None]
        ] = {}
        self._lock = asyncio.Lock()

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        store_id: str | None = None,
        customer_id: str | None = None,
        event_id: str | None = None,
    ) -> StreamEvent:
        async with self._lock:
            self._counter += 1
            seq_id = str(self._counter) if event_id is None else str(event_id)
            event = StreamEvent(
                id=seq_id,
                event=event_type,
                data=data,
                store_id=str(store_id) if store_id else None,
                customer_id=str(customer_id) if customer_id else None,
            )
            self._history.append(event)

            # Fan-out to matching active subscriber queues
            for sub_queue, sub_store_id, sub_cust_id in self._subscribers.values():
                if event.matches_scope(sub_store_id, sub_cust_id):
                    # Avoid blocking if a queue is full; put_nowait with maxsize drops oldest if needed
                    try:
                        sub_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        try:
                            _ = sub_queue.get_nowait()
                            sub_queue.put_nowait(event)
                        except (asyncio.QueueEmpty, asyncio.QueueFull):
                            pass

            return event

    async def subscribe(
        self,
        store_id: str | None = None,
        customer_id: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        sub_id = uuid.uuid4().hex
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=200)

        # 1. Replay missed historical events if Last-Event-ID is provided
        replay_events: list[StreamEvent] = []
        async with self._lock:
            if last_event_id is not None:
                # Find if last_event_id is an integer counter
                last_num = None
                try:
                    last_num = int(last_event_id)
                except ValueError:
                    pass

                for past_evt in self._history:
                    should_replay = False
                    if last_num is not None:
                        try:
                            if int(past_evt.id) > last_num:
                                should_replay = True
                        except ValueError:
                            if past_evt.id != last_event_id:
                                should_replay = True
                    elif past_evt.id != last_event_id:
                        should_replay = True

                    if should_replay and past_evt.matches_scope(store_id, customer_id):
                        replay_events.append(past_evt)

            self._subscribers[sub_id] = (queue, store_id, customer_id)

        try:
            # Yield any replayed events first
            for evt in replay_events:
                yield evt

            # Stream live events with 15-second heartbeat idle timeout
            while True:
                try:
                    live_evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield live_evt
                except TimeoutError:
                    yield StreamEvent(id="", event=":heartbeat", data={})
        finally:
            async with self._lock:
                self._subscribers.pop(sub_id, None)


# Default singleton instance
event_bus: EventTransport = InMemoryEventBus()


async def publish_event(
    event_type: str,
    data: dict[str, Any],
    store_id: str | None = None,
    customer_id: str | None = None,
    event_id: str | None = None,
) -> StreamEvent:
    return await event_bus.publish(
        event_type=event_type,
        data=data,
        store_id=store_id,
        customer_id=customer_id,
        event_id=event_id,
    )


async def subscribe_events(
    store_id: str | None = None,
    customer_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[StreamEvent]:
    async for evt in event_bus.subscribe(
        store_id=store_id,
        customer_id=customer_id,
        last_event_id=last_event_id,
    ):
        yield evt
