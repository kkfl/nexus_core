"""
Event store — persist events to Postgres for audit and debugging.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.events.schema import NexusEvent
from packages.shared.logging import redact_dict

logger = structlog.get_logger(__name__)


async def persist_event(
    db: AsyncSession,
    event: NexusEvent,
    stream_id: str | None = None,
) -> None:
    """
    Write an event to the ``bus_events`` table.

    Payload is redacted before storage (passwords, tokens, etc. are scrubbed).
    """
    from packages.shared.models.core import BusEvent

    row = BusEvent(
        id=event.event_id,
        event_type=event.event_type,
        event_version=event.event_version,
        occurred_at=event.occurred_at,
        produced_by=event.produced_by,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        actor_type=event.actor.type,
        actor_id=event.actor.id,
        tenant_id=event.tenant_id,
        severity=event.severity,
        tags=event.tags,
        payload=redact_dict(event.payload),
        payload_schema_version=event.payload_schema_version,
        idempotency_key=event.idempotency_key,
        stream_id=stream_id,
    )
    db.add(row)
    await db.flush()
    logger.debug(
        "event_persisted",
        event_type=event.event_type,
        event_id=event.event_id,
    )


async def query_events(
    db: AsyncSession,
    *,
    event_type: str | None = None,
    correlation_id: str | None = None,
    tenant_id: str | None = None,
    produced_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Query the event store for audit / debugging.
    Returns dicts ready for JSON serialisation.
    """
    from packages.shared.models.core import BusEvent

    q = select(BusEvent).order_by(BusEvent.created_at.desc())

    if event_type:
        q = q.where(BusEvent.event_type == event_type)
    if correlation_id:
        q = q.where(BusEvent.correlation_id == correlation_id)
    if tenant_id:
        q = q.where(BusEvent.tenant_id == tenant_id)
    if produced_by:
        q = q.where(BusEvent.produced_by == produced_by)

    q = q.limit(limit).offset(offset)

    result = await db.execute(q)
    rows = result.scalars().all()

    return [
        {
            "event_id": row.id,
            "event_type": row.event_type,
            "event_version": row.event_version,
            "occurred_at": row.occurred_at,
            "produced_by": row.produced_by,
            "correlation_id": row.correlation_id,
            "causation_id": row.causation_id,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "tenant_id": row.tenant_id,
            "severity": row.severity,
            "tags": row.tags,
            "payload": row.payload,
            "payload_schema_version": row.payload_schema_version,
            "idempotency_key": row.idempotency_key,
            "stream_id": row.stream_id,
            "created_at": str(row.created_at) if row.created_at else None,
        }
        for row in rows
    ]
