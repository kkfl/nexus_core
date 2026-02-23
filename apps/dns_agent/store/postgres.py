"""
Postgres store for DNS Agent — CRUD layer for zones, records, jobs, and audit events.
All operations use async SQLAlchemy sessions.
"""

from __future__ import annotations

import datetime
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.dns_agent.config import get_settings
from apps.dns_agent.models import DnsAuditEvent, DnsChangeJob, DnsRecord, DnsZone

logger = structlog.get_logger(__name__)

_engine = None
_session_factory = None


def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    _get_engine()
    async with _session_factory() as session, session.begin():
        yield session


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


async def get_zone(db: AsyncSession, zone_id: str) -> DnsZone | None:
    result = await db.execute(select(DnsZone).where(DnsZone.id == zone_id))
    return result.scalars().first()


async def get_zone_by_name(
    db: AsyncSession, tenant_id: str, env: str, zone_name: str
) -> DnsZone | None:
    result = await db.execute(
        select(DnsZone).where(
            DnsZone.tenant_id == tenant_id,
            DnsZone.env == env,
            DnsZone.zone_name == zone_name,
            DnsZone.is_active is True,
        )
    )
    return result.scalars().first()


async def list_zones(
    db: AsyncSession, tenant_id: str | None = None, env: str | None = None
) -> list[DnsZone]:
    q = select(DnsZone).where(DnsZone.is_active is True)
    if tenant_id:
        q = q.where(DnsZone.tenant_id == tenant_id)
    if env:
        q = q.where(DnsZone.env == env)
    result = await db.execute(q.order_by(DnsZone.tenant_id, DnsZone.zone_name))
    return list(result.scalars().all())


async def create_zone(
    db: AsyncSession, tenant_id: str, env: str, zone_name: str, provider: str
) -> DnsZone:
    zone = DnsZone(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        env=env,
        zone_name=zone_name,
        provider=provider,
    )
    db.add(zone)
    await db.flush()
    return zone


async def set_provider_zone_id(db: AsyncSession, zone: DnsZone, provider_zone_id: str) -> DnsZone:
    zone.provider_zone_id = provider_zone_id
    await db.flush()
    return zone


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


async def list_records(db: AsyncSession, zone_id: str) -> list[DnsRecord]:
    result = await db.execute(
        select(DnsRecord)
        .where(DnsRecord.zone_id == zone_id)
        .order_by(DnsRecord.record_type, DnsRecord.name)
    )
    return list(result.scalars().all())


async def get_record(
    db: AsyncSession, zone_id: str, record_type: str, name: str
) -> DnsRecord | None:
    result = await db.execute(
        select(DnsRecord).where(
            DnsRecord.zone_id == zone_id,
            DnsRecord.record_type == record_type,
            DnsRecord.name == name,
        )
    )
    return result.scalars().first()


async def upsert_record(
    db: AsyncSession,
    zone: DnsZone,
    record_type: str,
    name: str,
    value: str,
    ttl: int,
    priority: int | None,
    tags: dict | None,
    provider_record_id: str | None = None,
) -> DnsRecord:
    existing = await get_record(db, zone.id, record_type, name)
    now = datetime.datetime.utcnow()
    if existing:
        existing.value = value
        existing.ttl = ttl
        existing.priority = priority
        existing.tags = tags or {}
        if provider_record_id:
            existing.provider_record_id = provider_record_id
        existing.last_synced_at = now
        existing.updated_at = now
        await db.flush()
        return existing
    else:
        rec = DnsRecord(
            id=str(uuid.uuid4()),
            zone_id=zone.id,
            tenant_id=zone.tenant_id,
            env=zone.env,
            record_type=record_type,
            name=name,
            value=value,
            ttl=ttl,
            priority=priority,
            tags=tags or {},
            provider_record_id=provider_record_id,
            last_synced_at=now,
        )
        db.add(rec)
        await db.flush()
        return rec


async def delete_record_by_spec(
    db: AsyncSession, zone_id: str, record_type: str, name: str
) -> bool:
    rec = await get_record(db, zone_id, record_type, name)
    if not rec:
        return False
    await db.delete(rec)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Change Jobs
# ---------------------------------------------------------------------------


async def create_job(
    db: AsyncSession,
    tenant_id: str,
    env: str,
    zone_name: str,
    operation: str,
    payload: dict,
    service_id: str,
    correlation_id: str,
) -> DnsChangeJob:
    job = DnsChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        env=env,
        zone_name=zone_name,
        operation=operation,
        payload=payload,
        status="pending",
        attempts=0,
        created_by_service_id=service_id,
        correlation_id=correlation_id,
    )
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: str) -> DnsChangeJob | None:
    result = await db.execute(select(DnsChangeJob).where(DnsChangeJob.id == job_id))
    return result.scalars().first()


async def update_job_status(
    db: AsyncSession, job: DnsChangeJob, status: str, last_error: str | None = None
) -> DnsChangeJob:
    now = datetime.datetime.utcnow()
    job.status = status
    if status == "running":
        job.started_at = now
    elif status in ("succeeded", "failed"):
        job.completed_at = now
    if last_error is not None:
        job.last_error = last_error
    job.attempts = (job.attempts or 0) + 1
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def log_audit(
    db: AsyncSession,
    correlation_id: str,
    service_id: str,
    tenant_id: str,
    env: str,
    action: str,
    result: str,
    zone_name: str | None = None,
    record_type: str | None = None,
    record_name: str | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an audit event. Never logs credential values. Never raises."""
    try:
        event = DnsAuditEvent(
            id=str(uuid.uuid4()),
            correlation_id=correlation_id,
            service_id=service_id,
            tenant_id=tenant_id,
            env=env,
            action=action,
            zone_name=zone_name,
            record_type=record_type,
            record_name=record_name,
            result=result,
            reason=reason,
            ip_address=ip_address,
        )
        db.add(event)
        await db.flush()
    except Exception as exc:
        logger.error("dns_audit_write_failed", error=str(exc))
