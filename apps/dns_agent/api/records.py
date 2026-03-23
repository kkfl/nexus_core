"""Records router — GET /v1/records, POST /v1/records/upsert, POST /v1/records/delete."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.dns_agent.jobs.runner import dispatch_job
from apps.dns_agent.schemas import (
    BatchDeleteRequest,
    BatchUpsertRequest,
    JobCreateResponse,
    RecordOut,
)
from apps.dns_agent.store import postgres as store
from packages.shared.alerts import send_alert
from packages.shared.events.api import emit_event

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/records", tags=["records"])


@router.get("", response_model=list[RecordOut])
async def list_records(
    tenant_id: str = Query(...),
    env: str = Query(...),
    zone: str = Query(...),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[RecordOut]:
    """List DNS records for a zone. Returns Nexus desired state, not live provider state."""
    dns_zone = await store.get_zone_by_name(db, tenant_id, env, zone)
    if not dns_zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone}' not found for tenant={tenant_id} env={env}.",
        )
    records = await store.list_records(db, dns_zone.id)
    return [RecordOut.model_validate(r) for r in records]


@router.post("/upsert", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_upsert(
    payload: BatchUpsertRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> JobCreateResponse:
    """
    Batch upsert DNS records. Creates an async change job — returns job_id immediately.
    Poll GET /v1/jobs/{job_id} for status.

    If dry_run=true: validates the zone exists but does not create a job or modify any records.
    """
    zone = await store.get_zone_by_name(db, payload.tenant_id, payload.env, payload.zone)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Zone '{payload.zone}' not found."
        )

    if payload.dry_run:
        return JobCreateResponse(
            job_id="dry-run",
            status="dry_run",
            message=f"Dry run: would upsert {len(payload.records)} record(s) into {payload.zone}.",
        )

    job_payload = {
        "records": [r.model_dump() for r in payload.records],
    }
    job = await store.create_job(
        db,
        payload.tenant_id,
        payload.env,
        payload.zone,
        operation="upsert",
        payload=job_payload,
        service_id=identity.service_id,
        correlation_id=identity.correlation_id,
    )

    from apps.dns_agent.store.postgres import _session_factory

    dispatch_job(job, _session_factory)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=payload.tenant_id,
        env=payload.env,
        action="upsert_records",
        zone_name=payload.zone,
        result="queued",
        ip_address=identity.ip_address,
        reason=f"{len(payload.records)} record(s) queued in job {job.id}",
    )

    try:
        await emit_event(
            event_type="dns.record.upserted",
            payload={"zone": payload.zone, "count": len(payload.records), "job_id": job.id},
            produced_by="dns-agent",
            tenant_id=payload.tenant_id,
            correlation_id=identity.correlation_id,
            tags=["dns", "record", "upsert"],
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="dns.record.upserted")

    send_alert(
        "dns_record_upsert",
        identity.service_id,
        f"Zone: {payload.zone} — {len(payload.records)} record(s)",
    )

    # Telegram notification
    try:
        import os

        from apps.notifications_agent.client.notifications_client import NotificationsClient

        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="dns-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        rec_lines = ", ".join(f"{r.record_type} {r.name}" for r in payload.records[:5])
        await nc.notify(
            tenant_id=payload.tenant_id,
            env=payload.env,
            severity="info",
            channels=["telegram"],
            subject="\U0001f310 DNS Records Added",
            body=f"Zone: {payload.zone}\n{rec_lines}",
            idempotency_key=f"dns-upsert:{job.id}",
        )
    except Exception:
        logger.warning("telegram_notify_failed", action="dns_upsert")

    return JobCreateResponse(
        job_id=job.id,
        status="pending",
        message=f"Upsert job created for {len(payload.records)} record(s).",
    )


@router.post("/delete", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_delete(
    payload: BatchDeleteRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> JobCreateResponse:
    """Batch delete DNS records. Creates an async change job."""
    zone = await store.get_zone_by_name(db, payload.tenant_id, payload.env, payload.zone)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Zone '{payload.zone}' not found."
        )

    job_payload = {"records": [r.model_dump() for r in payload.records]}
    job = await store.create_job(
        db,
        payload.tenant_id,
        payload.env,
        payload.zone,
        operation="delete",
        payload=job_payload,
        service_id=identity.service_id,
        correlation_id=identity.correlation_id,
    )

    from apps.dns_agent.store.postgres import _session_factory

    dispatch_job(job, _session_factory)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=payload.tenant_id,
        env=payload.env,
        action="delete_records",
        zone_name=payload.zone,
        result="queued",
        ip_address=identity.ip_address,
    )

    try:
        await emit_event(
            event_type="dns.record.deleted",
            payload={"zone": payload.zone, "count": len(payload.records), "job_id": job.id},
            produced_by="dns-agent",
            tenant_id=payload.tenant_id,
            correlation_id=identity.correlation_id,
            tags=["dns", "record", "delete"],
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="dns.record.deleted")

    send_alert(
        "dns_record_delete",
        identity.service_id,
        f"Zone: {payload.zone} — {len(payload.records)} record(s)",
    )

    # Telegram notification
    try:
        import os

        from apps.notifications_agent.client.notifications_client import NotificationsClient

        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="dns-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        rec_lines = ", ".join(f"{r.record_type} {r.name}" for r in payload.records[:5])
        await nc.notify(
            tenant_id=payload.tenant_id,
            env=payload.env,
            severity="info",
            channels=["telegram"],
            subject="\U0001f5d1\ufe0f DNS Records Deleted",
            body=f"Zone: {payload.zone}\n{rec_lines}",
            idempotency_key=f"dns-delete:{job.id}",
        )
    except Exception:
        logger.warning("telegram_notify_failed", action="dns_delete")

    return JobCreateResponse(
        job_id=job.id,
        status="pending",
        message=f"Delete job created for {len(payload.records)} record(s).",
    )
