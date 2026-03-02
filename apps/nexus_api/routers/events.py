"""
Brain event bus admin endpoints.

Routes:
  GET  /events           — query event store (Postgres)
  GET  /events/streams   — list active Redis streams + consumer groups
  GET  /events/dlq       — view dead-letter queue entries
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.db import get_db
from packages.shared.events.store import query_events
from packages.shared.events.transport import EventBus

logger = structlog.get_logger(__name__)

router = APIRouter()

_bus: EventBus | None = None


def _get_bus() -> EventBus:
    global _bus
    if _bus is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _bus = EventBus.from_url(redis_url)
    return _bus


@router.get("")
async def list_events(
    db: AsyncSession = Depends(get_db),
    event_type: str | None = Query(None, description="Filter by event type"),
    correlation_id: str | None = Query(None, description="Filter by correlation ID"),
    tenant_id: str | None = Query(None, description="Filter by tenant"),
    produced_by: str | None = Query(None, description="Filter by producer service"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query the event store (Postgres) with optional filters."""
    events = await query_events(
        db,
        event_type=event_type,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        produced_by=produced_by,
        limit=limit,
        offset=offset,
    )
    return {"count": len(events), "events": events}


@router.get("/streams")
async def list_streams() -> dict[str, Any]:
    """List active Redis event streams with consumer group info."""
    bus = _get_bus()
    streams = await bus.list_streams()
    return {"count": len(streams), "streams": streams}


@router.get("/dlq")
async def list_dlq(
    count: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """View dead-letter queue entries."""
    bus = _get_bus()
    entries = await bus.read_dlq(count=count)
    return {"count": len(entries), "entries": entries}
