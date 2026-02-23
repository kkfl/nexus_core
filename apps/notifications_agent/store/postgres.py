"""
Postgres CRUD store for notifications_agent.
Job lifecycle, delivery tracking, template and routing rule management.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.notifications_agent.config import get_settings
from apps.notifications_agent.models import (
    NotificationAuditEvent,
    NotificationDelivery,
    NotificationJob,
    NotificationRoutingRule,
    NotificationTemplate,
)

_engine = None
_session_factory = None


def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_db():
    _get_engine()
    async with _session_factory() as session, session.begin():
        yield session


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


async def create_job(
    db: AsyncSession,
    *,
    tenant_id: str,
    env: str,
    severity: str,
    channels: list[str],
    idempotency_key: str,
    correlation_id: str,
    created_by_service_id: str,
    template_id: str | None = None,
    subject: str | None = None,
    body_hash: str,
    body_stored: str | None,
    sensitivity: str = "normal",
    context: dict | None = None,
    routing_rule_id: str | None = None,
    max_attempts: int = 3,
) -> NotificationJob:
    settings = get_settings()
    ttl = timedelta(hours=settings.job_idempotency_ttl_hours)
    job = NotificationJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        env=env,
        severity=severity,
        channels=channels,
        idempotency_key=idempotency_key,
        idempotency_expires_at=datetime.now(UTC) + ttl,
        correlation_id=correlation_id,
        created_by_service_id=created_by_service_id,
        template_id=template_id,
        subject=subject,
        body_hash=body_hash,
        body_stored=body_stored,
        sensitivity=sensitivity,
        context=context or {},
        routing_rule_id=routing_rule_id,
        max_attempts=max_attempts,
        status="pending",
    )
    db.add(job)
    return job


async def get_job_by_idempotency_key(db: AsyncSession, key: str) -> NotificationJob | None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(NotificationJob)
        .where(NotificationJob.idempotency_key == key)
        .where(NotificationJob.idempotency_expires_at > now)
    )
    return result.scalar_one_or_none()


async def get_job(db: AsyncSession, job_id: str) -> NotificationJob | None:
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(NotificationJob)
        .options(selectinload(NotificationJob.deliveries))
        .where(NotificationJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    tenant_id: str,
    env: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[NotificationJob]:
    q = select(NotificationJob).where(NotificationJob.tenant_id == tenant_id)
    if env:
        q = q.where(NotificationJob.env == env)
    if status:
        q = q.where(NotificationJob.status == status)
    q = q.order_by(NotificationJob.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def set_job_status(
    db: AsyncSession, job_id: str, status: str, completed_at: datetime | None = None
) -> None:
    vals = {"status": status}
    if completed_at:
        vals["completed_at"] = completed_at
    await db.execute(update(NotificationJob).where(NotificationJob.id == job_id).values(**vals))


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


async def create_delivery(
    db: AsyncSession, *, job_id: str, channel: str, destination_hash: str
) -> NotificationDelivery:
    d = NotificationDelivery(
        id=uuid.uuid4(),
        job_id=job_id,
        channel=channel,
        destination_hash=destination_hash,
        status="pending",
    )
    db.add(d)
    return d


async def update_delivery(db: AsyncSession, delivery_id: str, **kwargs) -> None:
    await db.execute(
        update(NotificationDelivery).where(NotificationDelivery.id == delivery_id).values(**kwargs)
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


async def get_template(db: AsyncSession, template_id: str) -> NotificationTemplate | None:
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    return result.scalar_one_or_none()


async def upsert_template(db: AsyncSession, **kwargs) -> NotificationTemplate:
    existing = await get_template(db, kwargs["id"])
    if existing:
        for k, v in kwargs.items():
            setattr(existing, k, v)
        return existing
    t = NotificationTemplate(**kwargs)
    db.add(t)
    return t


async def list_templates(db: AsyncSession, limit: int = 100) -> list[NotificationTemplate]:
    result = await db.execute(select(NotificationTemplate).limit(limit))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Routing Rules
# ---------------------------------------------------------------------------


async def upsert_routing_rule(db: AsyncSession, **kwargs) -> NotificationRoutingRule:
    result = await db.execute(
        select(NotificationRoutingRule)
        .where(NotificationRoutingRule.tenant_id == kwargs["tenant_id"])
        .where(NotificationRoutingRule.env == kwargs["env"])
        .where(NotificationRoutingRule.severity == kwargs["severity"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        for k, v in kwargs.items():
            setattr(existing, k, v)
        return existing
    r = NotificationRoutingRule(id=uuid.uuid4(), **kwargs)
    db.add(r)
    return r


async def list_routing_rules(
    db: AsyncSession, tenant_id: str, env: str | None = None
) -> list[NotificationRoutingRule]:
    q = select(NotificationRoutingRule).where(NotificationRoutingRule.tenant_id == tenant_id)
    if env:
        q = q.where(NotificationRoutingRule.env == env)
    result = await db.execute(q)
    return list(result.scalars().all())


async def resolve_routing_rule(
    db: AsyncSession, tenant_id: str, env: str, severity: str
) -> NotificationRoutingRule | None:
    """Find the most specific matching rule (exact severity, then wildcard)."""
    for sev in (severity, "*"):
        result = await db.execute(
            select(NotificationRoutingRule)
            .where(NotificationRoutingRule.tenant_id == tenant_id)
            .where(NotificationRoutingRule.env == env)
            .where(NotificationRoutingRule.severity == sev)
            .where(NotificationRoutingRule.enabled is True)
        )
        row = result.scalar_one_or_none()
        if row:
            return row
    return None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def list_audit(
    db: AsyncSession, tenant_id: str, limit: int = 100
) -> list[NotificationAuditEvent]:
    result = await db.execute(
        select(NotificationAuditEvent)
        .where(NotificationAuditEvent.tenant_id == tenant_id)
        .order_by(NotificationAuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
