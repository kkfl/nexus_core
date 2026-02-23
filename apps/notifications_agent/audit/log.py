"""
Audit writer for notifications_agent.
Every notification attempt, delivery, and auth event is logged here.
Content is hashed if sensitivity=sensitive. Destinations are always hashed.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.notifications_agent.models import NotificationAuditEvent

logger = structlog.get_logger(__name__)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_destination(destination: str) -> str:
    """SHA-256 of phone number, email address, or chat ID. Never stored raw."""
    return _hash(destination)


def hash_body(body: str) -> str:
    """SHA-256 of rendered message body."""
    return _hash(body)


async def write_audit(
    db: AsyncSession,
    *,
    correlation_id: str,
    service_id: str,
    tenant_id: str,
    env: str,
    action: str,
    result: str,
    job_id: Optional[str] = None,
    delivery_id: Optional[str] = None,
    channel: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write an audit event. Runs inside an existing session transaction."""
    event = NotificationAuditEvent(
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        result=result,
        job_id=job_id,
        delivery_id=delivery_id,
        channel=channel,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(event)
    logger.info(
        "notifications_audit",
        action=action,
        result=result,
        tenant_id=tenant_id,
        channel=channel,
        correlation_id=correlation_id,
    )
