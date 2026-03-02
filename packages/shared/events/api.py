"""
Developer-facing convenience API for publishing events.

    from packages.shared.events import emit_event

    await emit_event(
        event_type="dns.zone.imported",
        payload={"zone_name": "example.com"},
        produced_by="dns-agent",
    )
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from packages.shared.events.schema import EventActor, NexusEvent
from packages.shared.events.store import persist_event
from packages.shared.events.transport import EventBus

logger = structlog.get_logger(__name__)

# Module-level singleton — initialised lazily
_bus: EventBus | None = None


def _get_bus() -> EventBus:
    global _bus
    if _bus is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _bus = EventBus.from_url(redis_url)
    return _bus


async def emit_event(
    event_type: str,
    payload: dict[str, Any],
    produced_by: str,
    *,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    actor_type: str = "service",
    actor_id: str | None = None,
    severity: str = "info",
    tags: list[str] | None = None,
    idempotency_key: str | None = None,
    event_version: int = 1,
    payload_schema_version: int = 1,
    db=None,
) -> NexusEvent:
    """
    Build, publish (Redis), and optionally persist (Postgres) an event.

    ``correlation_id`` is auto-read from structlog context if not provided.
    ``db`` is an optional AsyncSession — if provided the event is also
    written to the ``bus_events`` table for audit.
    """
    # Auto-read correlation_id from structlog contextvars
    if correlation_id is None:
        ctx = structlog.contextvars.get_contextvars()
        correlation_id = ctx.get("correlation_id")

    event = NexusEvent(
        event_type=event_type,
        event_version=event_version,
        produced_by=produced_by,
        correlation_id=correlation_id or "",
        causation_id=causation_id,
        actor=EventActor(type=actor_type, id=actor_id or produced_by),
        tenant_id=tenant_id,
        severity=severity,
        tags=tags or [],
        payload=payload,
        payload_schema_version=payload_schema_version,
        idempotency_key=idempotency_key,
    )

    bus = _get_bus()
    stream_id = await bus.publish(event)

    logger.info(
        "event_emitted",
        event_type=event.event_type,
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        stream_id=stream_id,
    )

    # Persist to Postgres if a DB session is available
    if db is not None:
        try:
            await persist_event(db, event, stream_id=stream_id)
        except Exception:
            logger.warning(
                "event_persist_failed",
                event_type=event.event_type,
                event_id=event.event_id,
            )

    return event
