"""
Redis Streams transport for the Nexus event bus.

Provides at-least-once delivery, consumer groups, DLQ, and replay.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
import structlog

from packages.shared.events.schema import NexusEvent

logger = structlog.get_logger(__name__)

# How many times we retry a failed message before DLQ
MAX_DELIVERY_ATTEMPTS = 3
DLQ_STREAM = "nexus:events:dlq"
# Block for up to 2 seconds on XREADGROUP before looping
BLOCK_MS = 2000
# Read up to 10 messages per poll
BATCH_SIZE = 10
# Approximate max stream length (trimmed on XADD)
STREAM_MAXLEN = 10_000
# Idle threshold (ms) before a pending message is re-claimed
CLAIM_IDLE_MS = 60_000


EventHandler = Callable[[NexusEvent], Awaitable[None]]


class EventBus:
    """
    Redis Streams-backed event bus.

    Producer usage::

        bus = EventBus.from_url("redis://localhost:6379/0")
        await bus.publish(event)

    Consumer usage::

        await bus.subscribe(
            event_types=["dns.zone.*"],
            group="automation-agent",
            handler=my_handler,
        )
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> EventBus:
        return cls(aioredis.from_url(url, decode_responses=False))

    # ── Publish ───────────────────────────────────────────────────────────

    async def publish(self, event: NexusEvent) -> str:
        """
        Publish an event to its Redis Stream.

        Returns the stream entry ID assigned by Redis.
        """
        stream_key = event.stream_key()
        entry = event.to_stream_dict()
        # XADD with approximate MAXLEN to prevent unbounded growth
        stream_id: bytes = await self._redis.xadd(
            stream_key, entry, maxlen=STREAM_MAXLEN, approximate=True,  # type: ignore[arg-type]
        )
        sid = stream_id.decode() if isinstance(stream_id, bytes) else str(stream_id)
        logger.debug(
            "event_published",
            event_type=event.event_type,
            event_id=event.event_id,
            stream_key=stream_key,
            stream_id=sid,
        )
        return sid

    # ── Subscribe ─────────────────────────────────────────────────────────

    async def subscribe(
        self,
        event_types: list[str],
        group: str,
        handler: EventHandler,
        consumer_name: str | None = None,
    ) -> None:
        """
        Start consuming events from one or more streams.

        ``event_types`` may contain wildcards (e.g. "dns.*").
        The consumer group is created automatically if it doesn't exist.
        This method blocks and runs the consumer loop — call it inside
        ``asyncio.create_task()`` or equivalent.
        """
        consumer = consumer_name or f"{group}-worker"

        # Resolve wildcards → concrete stream keys
        stream_keys = await self._resolve_streams(event_types)
        if not stream_keys:
            logger.warning("event_subscribe_no_streams", patterns=event_types)
            return

        # Ensure consumer groups exist
        for key in stream_keys:
            await self._ensure_group(key, group)

        logger.info(
            "event_consumer_started",
            group=group,
            consumer=consumer,
            streams=stream_keys,
        )

        while True:
            try:
                # 1. Process new messages
                await self._poll_and_process(stream_keys, group, consumer, handler)
                # 2. Claim and retry idle pending messages (DLQ path)
                await self._claim_pending(stream_keys, group, consumer, handler)
            except asyncio.CancelledError:
                logger.info("event_consumer_cancelled", group=group)
                break
            except Exception:
                logger.exception("event_consumer_error", group=group)
                await asyncio.sleep(1)

    async def _poll_and_process(
        self,
        stream_keys: list[str],
        group: str,
        consumer: str,
        handler: EventHandler,
    ) -> None:
        """One poll iteration: read, process, ack/nack."""
        streams_arg = {k.encode(): b">" for k in stream_keys}

        results: list[Any] = await self._redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams=streams_arg,  # type: ignore[arg-type]
            count=BATCH_SIZE,
            block=BLOCK_MS,
        )

        if not results:
            return

        for stream_bytes, entries in results:
            stream_key = (
                stream_bytes.decode()
                if isinstance(stream_bytes, bytes)
                else str(stream_bytes)
            )
            for entry_id_bytes, fields in entries:
                entry_id = (
                    entry_id_bytes.decode()
                    if isinstance(entry_id_bytes, bytes)
                    else str(entry_id_bytes)
                )
                try:
                    event = NexusEvent.from_stream_dict(fields)
                    await handler(event)
                    await self._redis.xack(stream_key, group, entry_id)
                    logger.debug(
                        "event_acked",
                        event_type=event.event_type,
                        event_id=event.event_id,
                        stream_id=entry_id,
                    )
                except Exception:
                    logger.exception(
                        "event_handler_failed",
                        stream_key=stream_key,
                        entry_id=entry_id,
                    )
                    await self._maybe_dlq(stream_key, group, entry_id, fields)

    async def _maybe_dlq(
        self,
        stream_key: str,
        group: str,
        entry_id: str,
        fields: dict[bytes | str, bytes | str],
    ) -> None:
        """Move to DLQ if delivery attempts exceed threshold."""
        try:
            # XPENDING for this specific entry
            pending = await self._redis.xpending_range(
                stream_key, group, min=entry_id, max=entry_id, count=1
            )
            if pending and len(pending) > 0:
                delivery_count = pending[0].get("times_delivered", 1)
                if isinstance(delivery_count, bytes):
                    delivery_count = int(delivery_count)
                if delivery_count >= MAX_DELIVERY_ATTEMPTS:
                    # Move to DLQ
                    dlq_fields = dict(fields)
                    dlq_fields[b"_original_stream"] = stream_key.encode()
                    dlq_fields[b"_original_entry_id"] = entry_id.encode()
                    dlq_fields[b"_delivery_attempts"] = str(delivery_count).encode()
                    await self._redis.xadd(DLQ_STREAM, dlq_fields)  # type: ignore[arg-type]
                    await self._redis.xack(stream_key, group, entry_id)
                    logger.warning(
                        "event_moved_to_dlq",
                        stream_key=stream_key,
                        entry_id=entry_id,
                        delivery_count=delivery_count,
                    )
        except Exception:
            logger.exception("dlq_routing_error", stream_key=stream_key, entry_id=entry_id)

    async def _claim_pending(
        self,
        stream_keys: list[str],
        group: str,
        consumer: str,
        handler: EventHandler,
    ) -> None:
        """Claim idle pending messages and reprocess them.

        This ensures failed messages eventually reach MAX_DELIVERY_ATTEMPTS
        and get routed to the DLQ instead of sitting in PEL forever.
        """
        for stream_key in stream_keys:
            try:
                # XAUTOCLAIM: claim messages idle for > CLAIM_IDLE_MS
                _, claimed, _ = await self._redis.xautoclaim(
                    stream_key, group, consumer,
                    min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=BATCH_SIZE,
                )
                for entry_id_bytes, fields in claimed:
                    entry_id = (
                        entry_id_bytes.decode()
                        if isinstance(entry_id_bytes, bytes)
                        else str(entry_id_bytes)
                    )
                    try:
                        event = NexusEvent.from_stream_dict(fields)
                        await handler(event)
                        await self._redis.xack(stream_key, group, entry_id)
                        logger.debug("event_reclaimed_acked", entry_id=entry_id)
                    except Exception:
                        logger.warning("event_reclaim_failed", entry_id=entry_id)
                        await self._maybe_dlq(stream_key, group, entry_id, fields)
            except Exception:
                # XAUTOCLAIM may fail on older Redis or empty PEL — non-fatal
                pass

    # ── Replay ────────────────────────────────────────────────────────────

    async def replay(
        self,
        event_type: str,
        handler: EventHandler,
        from_id: str = "0-0",
        count: int = 100,
    ) -> int:
        """
        Replay events from a stream starting at ``from_id``.

        Returns the number of events replayed.
        """
        stream_key = f"nexus:events:{event_type}"
        total = 0

        results = await self._redis.xrange(stream_key, min=from_id, count=count)
        for entry_id_bytes, fields in results:
            event = NexusEvent.from_stream_dict(fields)
            await handler(event)
            total += 1

        logger.info("event_replay_complete", event_type=event_type, count=total)
        return total

    # ── Admin ─────────────────────────────────────────────────────────────

    async def list_streams(self) -> list[dict[str, Any]]:
        """List all nexus event streams with lengths and group info."""
        streams: list[dict[str, Any]] = []
        cursor: bytes | int = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match=b"nexus:events:*", count=100
            )
            for key_bytes in keys:
                key = key_bytes.decode() if isinstance(key_bytes, bytes) else str(key_bytes)
                length = await self._redis.xlen(key)
                groups = await self._redis.xinfo_groups(key)
                streams.append(
                    {
                        "stream": key,
                        "length": length,
                        "groups": [
                            {
                                "name": (
                                    g["name"].decode()
                                    if isinstance(g.get("name"), bytes)
                                    else g.get("name")
                                ),
                                "consumers": g.get("consumers", 0),
                                "pending": g.get("pending", 0),
                                "last_delivered_id": (
                                    g["last-delivered-id"].decode()
                                    if isinstance(g.get("last-delivered-id"), bytes)
                                    else g.get("last-delivered-id")
                                ),
                            }
                            for g in groups
                        ],
                    }
                )
            if cursor == 0:
                break
        return streams

    async def read_dlq(self, count: int = 50) -> list[dict[str, Any]]:
        """Read entries from the dead-letter queue."""
        entries: list[dict[str, Any]] = []
        results = await self._redis.xrange(DLQ_STREAM, count=count)
        for entry_id_bytes, fields in results:
            entry_id = (
                entry_id_bytes.decode()
                if isinstance(entry_id_bytes, bytes)
                else str(entry_id_bytes)
            )
            try:
                event = NexusEvent.from_stream_dict(fields)
                entries.append(
                    {
                        "dlq_entry_id": entry_id,
                        "event": event.model_dump(),
                        "original_stream": _decode_field(fields, b"_original_stream"),
                        "original_entry_id": _decode_field(fields, b"_original_entry_id"),
                        "delivery_attempts": _decode_field(fields, b"_delivery_attempts"),
                    }
                )
            except Exception:
                entries.append({"dlq_entry_id": entry_id, "raw": str(fields)})
        return entries

    # ── Internals ─────────────────────────────────────────────────────────

    async def _ensure_group(self, stream_key: str, group: str) -> None:
        try:
            await self._redis.xgroup_create(
                stream_key, group, id="0", mkstream=True
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # group already exists
            else:
                raise

    async def _resolve_streams(self, patterns: list[str]) -> list[str]:
        """
        Resolve event type patterns (with wildcards) to existing stream keys.
        Also creates streams for exact (non-wildcard) patterns so they're
        ready for XREADGROUP even if no events have been published yet.
        """
        keys: set[str] = set()

        for pat in patterns:
            if "*" in pat or "?" in pat:
                # Scan for matching streams
                cursor: bytes | int = 0
                while True:
                    cursor, found = await self._redis.scan(
                        cursor=cursor,
                        match=f"nexus:events:{pat}".encode(),
                        count=100,
                    )
                    for k in found:
                        keys.add(
                            k.decode() if isinstance(k, bytes) else str(k)
                        )
                    if cursor == 0:
                        break
            else:
                # Exact event type → deterministic stream key
                keys.add(f"nexus:events:{pat}")

        return sorted(keys)

    async def close(self) -> None:
        await self._redis.aclose()


def _decode_field(fields: dict[Any, Any], key: bytes) -> str | None:
    val = fields.get(key)
    if val is None:
        return None
    return val.decode() if isinstance(val, bytes) else str(val)
