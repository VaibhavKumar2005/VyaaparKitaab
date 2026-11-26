"""
Event Bus Service for Real-Time Streaming (SSE / WebSockets).

Architecture & Transport Choice:
---------------------------------
In a horizontally scaled, multi-instance deployment behind a reverse proxy (e.g. NGINX
or Azure Container Apps), individual application processes do not share memory. An incoming
webhook processed by Worker Node A must publish an event that reaches a long-lived SSE stream
connected to Worker Node B.

Message delivery is placed behind the `EventTransport` protocol:
- `InMemoryEventBus` (default for local dev & unit tests): per-subscriber `asyncio.Queue`
  instances with a bounded ring buffer for `Last-Event-ID` reconnection replay.
- `PostgresEventBus` (`EVENT_BUS_BACKEND=postgres`): wraps local per-subscriber queues and
  fans events across replicas over a dedicated non-pooled `asyncpg` connection using
  PostgreSQL `LISTEN` / `NOTIFY` (`pg_notify`), spilling payloads larger than ~7.5 KB to
  `sse_event_payloads` so PostgreSQL's 8 KB `NOTIFY` limit is never exceeded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import ssl
import uuid
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit

import asyncpg

from app.cores.config import settings

logger = logging.getLogger(__name__)

MAX_NOTIFY_BYTES = 7500
_VALID_CHANNEL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _to_asyncpg_dsn(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _build_ssl_arg(dsn: str, verify: bool) -> ssl.SSLContext | bool:
    hostname = urlsplit(dsn).hostname
    if hostname in {"localhost", "127.0.0.1", "db", None}:
        return False
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


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
    """Interface for event bus transports (`InMemoryEventBus`, `PostgresEventBus`)."""

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

        replay_events: list[StreamEvent] = []
        async with self._lock:
            if last_event_id is not None:
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
            for evt in replay_events:
                yield evt

            while True:
                try:
                    live_evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield live_evt
                except TimeoutError:
                    yield StreamEvent(id="", event=":heartbeat", data={})
        finally:
            async with self._lock:
                self._subscribers.pop(sub_id, None)


class PostgresEventBus:
    """
    Cross-replica PostgreSQL `LISTEN` / `NOTIFY` event bus.

    - Uses a dedicated `asyncpg` connection per replica (`DATABASE_DIRECT_URL` or `DATABASE_URL`)
      so PgBouncer transaction pooling never drops session-level `LISTEN` registrations.
    - Fans out immediately to local `InMemoryEventBus` queues on the publishing replica and
      broadcasts via `SELECT pg_notify($1, $2)` to all peer replicas.
    - Automatically spills payloads > 7,500 UTF-8 bytes into `sse_event_payloads` and sends a
      compact pointer frame so PostgreSQL's 8,000-byte `NOTIFY` ceiling is never exceeded.
    """

    def __init__(
        self,
        dsn: str,
        *,
        channel: str = "vk_events",
        max_history: int = 1000,
        ssl_verify: bool = True,
    ) -> None:
        if not _VALID_CHANNEL_RE.match(channel):
            raise ValueError(f"Invalid PostgreSQL LISTEN/NOTIFY channel name: {channel!r}")
        self._dsn = _to_asyncpg_dsn(dsn)
        self._channel = channel
        self._ssl = _build_ssl_arg(self._dsn, ssl_verify)
        self._instance_id = uuid.uuid4().hex
        self._local = InMemoryEventBus(max_history=max_history)
        self._listen_conn: asyncpg.Connection | None = None
        self._pub_conn: asyncpg.Connection | None = None
        self._listen_lock = asyncio.Lock()
        self._pub_lock = asyncio.Lock()
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    async def ensure_listener(self) -> None:
        """Opens the replica's dedicated LISTEN connection if not already active."""
        async with self._listen_lock:
            if self._listen_conn is not None and not self._listen_conn.is_closed():
                return
            conn = await asyncpg.connect(self._dsn, ssl=self._ssl)
            await conn.add_listener(self._channel, self._on_notify)
            self._listen_conn = conn

    async def _get_pub_conn(self) -> asyncpg.Connection:
        if self._pub_conn is None or self._pub_conn.is_closed():
            self._pub_conn = await asyncpg.connect(self._dsn, ssl=self._ssl)
        return self._pub_conn

    def _on_notify(self, _conn: Any, _pid: int, _channel: str, payload: str) -> None:
        try:
            envelope = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed PostgresEventBus NOTIFY frame")
            return

        if envelope.get("origin") == self._instance_id:
            return

        task = asyncio.create_task(self._deliver_remote_envelope(envelope))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _deliver_remote_envelope(self, envelope: dict[str, Any]) -> None:
        event_id = str(envelope.get("id") or uuid.uuid4().hex)
        event_type = str(envelope.get("event") or "message")
        store_id = envelope.get("store_id")
        customer_id = envelope.get("customer_id")

        if envelope.get("overflow"):
            data = await self._fetch_overflow_payload(event_id)
        else:
            raw_data = envelope.get("data")
            data = raw_data if isinstance(raw_data, dict) else {}

        await self._local.publish(
            event_type=event_type,
            data=data,
            store_id=store_id,
            customer_id=customer_id,
            event_id=event_id,
        )

    async def _fetch_overflow_payload(self, event_id: str) -> dict[str, Any]:
        conn = await asyncpg.connect(self._dsn, ssl=self._ssl)
        try:
            row = await conn.fetchrow(
                "SELECT payload_json FROM sse_event_payloads WHERE event_id = $1",
                event_id,
            )
            if row and row["payload_json"]:
                parsed = json.loads(row["payload_json"])
                if isinstance(parsed, dict):
                    return parsed
        except (OSError, asyncpg.PostgresError, json.JSONDecodeError, TypeError):
            logger.warning("Failed to fetch overflow SSE payload for event_id=%s", event_id, exc_info=True)
        finally:
            await conn.close()
        return {"truncated": True, "event_id": event_id}

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        store_id: str | None = None,
        customer_id: str | None = None,
        event_id: str | None = None,
    ) -> StreamEvent:
        resolved_id = str(event_id) if event_id is not None else f"pg_{uuid.uuid4().hex[:16]}"
        local_evt = await self._local.publish(
            event_type=event_type,
            data=data,
            store_id=store_id,
            customer_id=customer_id,
            event_id=resolved_id,
        )

        envelope: dict[str, Any] = {
            "id": local_evt.id,
            "event": event_type,
            "store_id": local_evt.store_id,
            "customer_id": local_evt.customer_id,
            "origin": self._instance_id,
            "data": data,
        }
        notify_text = json.dumps(envelope, default=_json_default)

        async with self._pub_lock:
            conn = await self._get_pub_conn()
            try:
                if len(notify_text.encode("utf-8")) > MAX_NOTIFY_BYTES:
                    full_data_json = json.dumps(data, default=_json_default)
                    await conn.execute(
                        "DELETE FROM sse_event_payloads WHERE created_at < now() - interval '1 hour'"
                    )
                    await conn.execute(
                        """
                        INSERT INTO sse_event_payloads (event_id, event_type, store_id, customer_id, payload_json)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (event_id) DO UPDATE SET payload_json = EXCLUDED.payload_json
                        """,
                        local_evt.id[:180],
                        event_type[:100],
                        local_evt.store_id[:64] if local_evt.store_id else None,
                        local_evt.customer_id[:64] if local_evt.customer_id else None,
                        full_data_json,
                    )
                    notify_text = json.dumps(
                        {
                            "id": local_evt.id,
                            "event": event_type,
                            "store_id": local_evt.store_id,
                            "customer_id": local_evt.customer_id,
                            "origin": self._instance_id,
                            "overflow": True,
                        }
                    )
                await conn.execute("SELECT pg_notify($1, $2)", self._channel, notify_text)
            except (OSError, asyncpg.PostgresError):
                logger.warning("PostgresEventBus pg_notify failed; resetting publisher connection", exc_info=True)
                try:
                    await conn.close()
                except (OSError, asyncpg.PostgresError) as close_exc:
                    logger.debug("Ignored publisher close error: %s", close_exc)
                self._pub_conn = None

        return local_evt

    async def subscribe(
        self,
        store_id: str | None = None,
        customer_id: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        await self.ensure_listener()
        async for evt in self._local.subscribe(
            store_id=store_id,
            customer_id=customer_id,
            last_event_id=last_event_id,
        ):
            yield evt

    async def close(self) -> None:
        for task in list(self._bg_tasks):
            task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        self._bg_tasks.clear()

        async with self._listen_lock:
            if self._listen_conn is not None and not self._listen_conn.is_closed():
                try:
                    await self._listen_conn.remove_listener(self._channel, self._on_notify)
                except (OSError, asyncpg.PostgresError) as rm_exc:
                    logger.debug("Ignored remove_listener error on close: %s", rm_exc)
                await self._listen_conn.close()
            self._listen_conn = None

        async with self._pub_lock:
            if self._pub_conn is not None and not self._pub_conn.is_closed():
                await self._pub_conn.close()
            self._pub_conn = None


def create_event_bus() -> EventTransport:
    backend = (settings.EVENT_BUS_BACKEND or "memory").strip().lower()
    if backend == "postgres":
        dsn = (settings.DATABASE_DIRECT_URL or "").strip() or settings.DATABASE_URL
        return PostgresEventBus(
            dsn=dsn,
            channel=settings.EVENT_BUS_CHANNEL,
            ssl_verify=settings.DB_SSL_VERIFY,
        )
    return InMemoryEventBus()


# Configured singleton instance ("memory" by default, "postgres" when EVENT_BUS_BACKEND=postgres)
event_bus: EventTransport = create_event_bus()


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
