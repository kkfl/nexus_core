"""
Lightweight metrics instrumentation helper.
Emits structured MetricEvent rows into Postgres for pilot telemetry.
"""
import structlog
from typing import Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from packages.shared.models.core import MetricEvent

logger = structlog.get_logger()


async def emit(
    db: AsyncSession,
    name: str,
    value: Optional[float] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write a single metric event to the database asynchronously.
    This is fire-and-forget: errors are logged but never raised.
    """
    try:
        event = MetricEvent(name=name, value=value, meta_data=meta or {})
        db.add(event)
        await db.flush()
        logger.debug("metric_emitted", name=name, value=value)
    except Exception as exc:
        logger.warning("metric_emit_failed", name=name, error=str(exc))
