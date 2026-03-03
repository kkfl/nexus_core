"""
Job worker for the Server Agent.
Polls server_change_jobs, executes operations via provider adapters,
emits server.* events, and writes audit entries.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.adapters.factory import get_adapter
from apps.server_agent.client.vault_client import ServerVaultClient
from apps.server_agent.config import get_settings
from apps.server_agent.models import (
    ServerAuditEvent,
    ServerBackup,
    ServerChangeJob,
    ServerHost,
    ServerInstance,
    ServerSnapshot,
)
from apps.server_agent.store.postgres import _get_session_factory

logger = structlog.get_logger(__name__)

# Event names
EVENT_MAP = {
    "create_instance": "server.created",
    "delete_instance": "server.deleted",
    "start": "server.started",
    "stop": "server.stopped",
    "reboot": "server.rebooted",
    "rebuild": "server.rebuilt",
    "create_snapshot": "server.snapshot.created",
    "delete_snapshot": "server.snapshot.deleted",
    "restore_snapshot": "server.snapshot.restored",
    "create_backup": "server.backup.created",
    "restore_backup": "server.backup.restored",
    "set_backup_schedule": "server.backup.scheduled",
    "disable_backups": "server.backup.disabled",
    "sync": "server.sync.completed",
}


async def _emit_event(event_type: str, payload: dict, correlation_id: str) -> None:
    """Emit event to Redis Streams (best-effort). Also persisted via bus_events."""
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        r = aioredis.from_url(settings.redis_url)
        await r.xadd(
            "nexus:events",
            {
                "type": event_type,
                "correlation_id": correlation_id,
                **{k: str(v) for k, v in payload.items()},
            },
        )
        await r.aclose()
    except Exception as exc:
        logger.warning("event_emit_failed", event_type=event_type, error=str(exc))


async def _execute_job(job: ServerChangeJob, db: AsyncSession) -> None:
    """Execute a single job."""
    payload = job.payload or {}
    correlation_id = job.correlation_id or str(uuid.uuid4())

    structlog.contextvars.bind_contextvars(
        job_id=job.id, operation=job.operation, correlation_id=correlation_id
    )

    # Resolve host + adapter
    host_id = payload.get("host_id")
    server_id = payload.get("server_id") or job.instance_id

    # Find the host
    host = None
    if host_id:
        host = await db.get(ServerHost, host_id)
    elif server_id:
        server = await db.get(ServerInstance, server_id)
        if server:
            host = await db.get(ServerHost, server.host_id)

    if not host:
        raise RuntimeError(f"Cannot resolve host for job {job.id}")

    vault = ServerVaultClient()
    secret = await vault.get_secret(
        alias=host.secret_alias,
        tenant_id=host.tenant_id,
        env=host.env,
        reason=f"job_{job.operation}",
        correlation_id=correlation_id,
    )
    adapter = await get_adapter(host.provider, host.config, secret)

    provider_id = payload.get("provider_instance_id", "")

    # Execute based on operation
    if job.operation == "create_instance":
        from apps.server_agent.adapters.base import CreateInstanceSpec

        spec = CreateInstanceSpec(
            label=payload["label"],
            hostname=payload["hostname"],
            region=payload["region"],
            plan=payload["plan"],
            os_id=payload["os_id"],
            ssh_keys=payload.get("ssh_keys", []),
            tags=payload.get("tags", {}),
        )
        meta = await adapter.create_instance(spec)

        # Create server_instances record
        instance = ServerInstance(
            id=str(uuid.uuid4()),
            host_id=host.id,
            tenant_id=host.tenant_id,
            env=host.env,
            provider=host.provider,
            provider_instance_id=meta.provider_instance_id,
            label=meta.label,
            hostname=meta.hostname,
            os=meta.os,
            plan=meta.plan,
            region=meta.region,
            ip_v4=meta.ip_v4,
            ip_v6=meta.ip_v6,
            status=meta.status,
            power_status=meta.power_status,
            vcpu_count=meta.vcpu_count,
            ram_mb=meta.ram_mb,
            disk_gb=meta.disk_gb,
            tags=meta.tags,
            last_synced_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(instance)
        job.instance_id = instance.id

    elif job.operation == "delete_instance":
        await adapter.delete_instance(provider_id)
        if server_id:
            server = await db.get(ServerInstance, server_id)
            if server:
                await db.delete(server)

    elif job.operation in ("start", "stop", "reboot"):
        fn = getattr(adapter, job.operation)
        await fn(provider_id)
        if server_id:
            server = await db.get(ServerInstance, server_id)
            if server:
                new_power = (
                    "running"
                    if job.operation == "start"
                    else ("stopped" if job.operation == "stop" else server.power_status)
                )
                server.power_status = new_power
                server.status = "running" if new_power == "running" else "stopped"

    elif job.operation == "rebuild":
        await adapter.rebuild_instance(provider_id, payload.get("os_id", ""))

    elif job.operation == "create_snapshot":
        meta = await adapter.create_snapshot(provider_id, payload.get("name", "snapshot"))
        snap = ServerSnapshot(
            id=str(uuid.uuid4()),
            instance_id=server_id,
            provider_snapshot_id=meta.provider_snapshot_id,
            name=meta.name,
            status="pending",
        )
        db.add(snap)

    elif job.operation == "delete_snapshot":
        await adapter.delete_snapshot(payload.get("provider_snapshot_id", ""))
        snap_id = payload.get("snapshot_id")
        if snap_id:
            snap = await db.get(ServerSnapshot, snap_id)
            if snap:
                await db.delete(snap)

    elif job.operation == "restore_snapshot":
        await adapter.restore_snapshot(provider_id, payload.get("provider_snapshot_id", ""))

    elif job.operation == "create_backup":
        meta = await adapter.create_backup(provider_id)
        backup = ServerBackup(
            id=str(uuid.uuid4()),
            instance_id=server_id,
            provider_backup_id=meta.provider_backup_id,
            backup_type=meta.backup_type,
            status="pending",
        )
        db.add(backup)

    elif job.operation == "restore_backup":
        await adapter.restore_backup(provider_id, payload.get("provider_backup_id", ""))

    elif job.operation == "set_backup_schedule":
        from apps.server_agent.adapters.base import BackupScheduleSpec

        schedule = BackupScheduleSpec(
            schedule_type=payload["schedule_type"],
            hour=payload.get("hour", 0),
            dow=payload.get("dow"),
            dom=payload.get("dom"),
        )
        await adapter.set_backup_schedule(provider_id, schedule)

    elif job.operation == "disable_backups":
        await adapter.disable_backups(provider_id)

    elif job.operation == "sync":
        instances = await adapter.list_instances()
        added = 0
        for meta in instances:
            existing = await db.execute(
                select(ServerInstance).where(
                    ServerInstance.host_id == host.id,
                    ServerInstance.provider_instance_id == meta.provider_instance_id,
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                # Update existing record with fresh data
                existing_row.label = meta.label
                existing_row.hostname = meta.hostname
                existing_row.os = meta.os
                existing_row.plan = meta.plan
                existing_row.region = meta.region
                existing_row.ip_v4 = meta.ip_v4
                existing_row.ip_v6 = meta.ip_v6
                existing_row.status = meta.status
                existing_row.power_status = meta.power_status
                existing_row.vcpu_count = meta.vcpu_count
                existing_row.ram_mb = meta.ram_mb
                existing_row.disk_gb = meta.disk_gb
                existing_row.last_synced_at = datetime.datetime.now(datetime.timezone.utc)
                continue
            db.add(
                ServerInstance(
                    id=str(uuid.uuid4()),
                    host_id=host.id,
                    tenant_id=host.tenant_id,
                    env=host.env,
                    provider=host.provider,
                    provider_instance_id=meta.provider_instance_id,
                    label=meta.label,
                    hostname=meta.hostname,
                    os=meta.os,
                    plan=meta.plan,
                    region=meta.region,
                    ip_v4=meta.ip_v4,
                    ip_v6=meta.ip_v6,
                    status=meta.status,
                    power_status=meta.power_status,
                    vcpu_count=meta.vcpu_count,
                    ram_mb=meta.ram_mb,
                    disk_gb=meta.disk_gb,
                    tags=meta.tags,
                    last_synced_at=datetime.datetime.now(datetime.timezone.utc),
                )
            )
            added += 1
        payload["added"] = added
        payload["total"] = len(instances)

    else:
        raise ValueError(f"Unknown operation: {job.operation}")


async def process_pending_jobs() -> int:
    """Process all pending jobs. Returns count of jobs processed."""
    settings = get_settings()
    factory = _get_session_factory()
    processed = 0

    async with factory() as db:
        result = await db.execute(
            select(ServerChangeJob)
            .where(ServerChangeJob.status == "pending")
            .order_by(ServerChangeJob.created_at)
            .limit(10)
        )
        jobs = result.scalars().all()

        for job in jobs:
            correlation_id = job.correlation_id or str(uuid.uuid4())
            try:
                # Mark running
                job.status = "running"
                job.attempts += 1
                job.started_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()

                await _execute_job(job, db)

                # Mark succeeded
                job.status = "succeeded"
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()

                # Emit event
                event_type = EVENT_MAP.get(job.operation, f"server.{job.operation}")
                await _emit_event(
                    event_type, {"job_id": job.id, **(job.payload or {})}, correlation_id
                )

                # Audit
                db.add(
                    ServerAuditEvent(
                        id=str(uuid.uuid4()),
                        correlation_id=correlation_id,
                        service_id="server-agent",
                        tenant_id=job.tenant_id,
                        env=job.env,
                        action=job.operation,
                        instance_label=str((job.payload or {}).get("label", "")),
                        provider="",
                        result="success",
                    )
                )
                await db.commit()

                logger.info("job_completed", job_id=job.id, operation=job.operation)
                processed += 1

            except Exception as exc:
                logger.error("job_failed", job_id=job.id, error=str(exc))
                job.status = "failed" if job.attempts >= settings.job_max_attempts else "pending"
                job.last_error = str(exc)[:1000]  # Truncate, never include credentials
                job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                await db.commit()

                # Emit failure event
                await _emit_event(
                    "server.job.failed",
                    {"job_id": job.id, "operation": job.operation, "error": str(exc)[:200]},
                    correlation_id,
                )

                # Audit failure
                db.add(
                    ServerAuditEvent(
                        id=str(uuid.uuid4()),
                        correlation_id=correlation_id,
                        service_id="server-agent",
                        tenant_id=job.tenant_id,
                        env=job.env,
                        action=job.operation,
                        result="error",
                        reason=str(exc)[:500],
                    )
                )
                await db.commit()
                processed += 1

    return processed


async def run_worker_loop() -> None:
    """Main worker loop -- polls for pending jobs."""
    settings = get_settings()
    logger.info("job_worker_started", poll_interval=settings.job_poll_interval)

    while True:
        try:
            count = await process_pending_jobs()
            if count > 0:
                logger.info("job_worker_batch", processed=count)
        except Exception as exc:
            logger.error("job_worker_error", error=str(exc))

        await asyncio.sleep(settings.job_poll_interval)
