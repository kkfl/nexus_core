"""
POST /v1/notify — main notification endpoint
GET  /v1/notifications/{id}
GET  /v1/notifications
POST /v1/notify/{job_id}/replay
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.notifications_agent import metrics
from apps.notifications_agent.audit.log import hash_body, write_audit
from apps.notifications_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.notifications_agent.queue.runner import dispatch_job
from apps.notifications_agent.routing.engine import resolve_channels
from apps.notifications_agent.schemas import DeliveryOut, JobOut, NotifyRequest, NotifyResponse
from apps.notifications_agent.store import postgres as store
from apps.notifications_agent.templates.engine import render_template

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["notify"])


def _job_to_out(job) -> JobOut:
    deliveries = []
    for d in job.deliveries or []:
        deliveries.append(
            DeliveryOut(
                id=str(d.id),
                channel=d.channel,
                status=d.status,
                destination_hash=d.destination_hash,
                provider_msg_id=d.provider_msg_id,
                attempt=d.attempt,
                error_code=d.error_code,
                sent_at=d.sent_at,
            )
        )
    return JobOut(
        id=str(job.id),
        tenant_id=job.tenant_id,
        env=job.env,
        severity=job.severity,
        status=job.status,
        channels=job.channels,
        template_id=job.template_id,
        sensitivity=job.sensitivity,
        attempts=job.attempts,
        correlation_id=job.correlation_id,
        created_at=job.created_at,
        completed_at=job.completed_at,
        deliveries=deliveries,
    )


@router.post("/notify", response_model=NotifyResponse, status_code=202)
async def notify(
    req: NotifyRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    metrics.inc("notification_requests_total")
    correlation_id = req.correlation_id or identity.correlation_id or str(uuid.uuid4())

    # Idempotency check
    existing = await store.get_job_by_idempotency_key(db, req.idempotency_key)
    if existing:
        await write_audit(
            db,
            correlation_id=correlation_id,
            service_id=identity.service_id,
            tenant_id=req.tenant_id,
            env=req.env,
            action="notify",
            result="dedup",
            job_id=str(existing.id),
            ip_address=identity.ip_address,
        )
        return NotifyResponse(
            job_id=str(existing.id),
            status=existing.status,
            message="Duplicate request — returning existing job.",
            idempotency_key=req.idempotency_key,
        )

    # Resolve channels via routing engine
    channels, rule_config = await resolve_channels(
        db,
        tenant_id=req.tenant_id,
        env=req.env,
        severity=req.severity,
        requested_channels=req.channels,
    )
    if not channels:
        raise HTTPException(status_code=400, detail="No channels resolved for this notification.")

    # Render template
    db_tpl = await store.get_template(db, req.template_id) if req.template_id else None
    subject, body = render_template(
        req.template_id or "generic",
        req.context,
        subject_override=req.subject,
        body_override=req.body,
        db_template_subject=db_tpl.subject_template if db_tpl else None,
        db_template_body=db_tpl.body_template if db_tpl else None,
    )

    if not body:
        raise HTTPException(status_code=400, detail="Message body is empty after rendering.")

    body_hash = hash_body(body)
    body_stored = body if req.sensitivity == "normal" else None

    # Create job record
    job = await store.create_job(
        db,
        tenant_id=req.tenant_id,
        env=req.env,
        severity=req.severity,
        channels=channels,
        idempotency_key=req.idempotency_key,
        correlation_id=correlation_id,
        created_by_service_id=identity.service_id,
        template_id=req.template_id,
        subject=subject,
        body_hash=body_hash,
        body_stored=body_stored,
        sensitivity=req.sensitivity,
        context=req.context,
    )
    job_id = str(job.id)

    await write_audit(
        db,
        correlation_id=correlation_id,
        service_id=identity.service_id,
        tenant_id=req.tenant_id,
        env=req.env,
        action="notify",
        result="ok",
        job_id=job_id,
        ip_address=identity.ip_address,
    )

    # Build channel configs (merging routing rule config + per-channel destinations)
    channel_configs = {}
    if rule_config:
        for ch in channels:
            channel_configs[ch] = {"severity": req.severity, **rule_config}

    # Dispatch async — returns immediately
    await dispatch_job(
        job_id=job_id,
        tenant_id=req.tenant_id,
        env=req.env,
        channels=channels,
        subject=subject,
        body=body,
        correlation_id=correlation_id,
        destinations=req.destinations,
        channel_configs=channel_configs,
    )

    return NotifyResponse(
        job_id=job_id,
        status="pending",
        message=f"Delivery queued for {len(channels)} channel(s).",
        idempotency_key=req.idempotency_key,
    )


@router.get("/notifications/{job_id}", response_model=JobOut)
async def get_notification(
    job_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    job = await store.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_to_out(job)


@router.get("/notifications", response_model=list[JobOut])
async def list_notifications(
    tenant_id: str = Query(...),
    env: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    jobs = await store.list_jobs(db, tenant_id=tenant_id, env=env, status=status, limit=limit)
    return [_job_to_out(j) for j in jobs]


@router.post("/notify/{job_id}/replay", status_code=202)
async def replay_job(
    job_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    """Re-enqueue a failed/partial job (admin DLQ replay)."""
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")

    job = await store.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in ("failed", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Job status is '{job.status}'; only failed/partial jobs can be replayed.",
        )

    body = job.body_stored or ""
    if not body:
        raise HTTPException(
            status_code=422, detail="Cannot replay: body was not stored (sensitivity=sensitive)."
        )

    await store.set_job_status(db, job_id, "pending")
    await dispatch_job(
        job_id=job_id,
        tenant_id=job.tenant_id,
        env=job.env,
        channels=job.channels,
        subject=job.subject,
        body=body,
        correlation_id=job.correlation_id,
    )
    return {"job_id": job_id, "status": "pending", "message": "Job re-queued for replay."}
