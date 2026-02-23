"""
DNS change job runner — executes queued change jobs asynchronously.

Job lifecycle: pending → running → succeeded | failed
- Max 3 attempts with exponential backoff before marking failed.
- Error messages stored in last_error (credential values are never included).
- Runs as asyncio background tasks within the uvicorn process (V2 → Redis/Worker).
"""
from __future__ import annotations

import asyncio
import datetime
import random
from typing import Callable, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.adapters.base import RecordSpec
from apps.dns_agent.adapters.factory import get_adapter
from apps.dns_agent.config import get_settings
from apps.dns_agent.models import DnsChangeJob
from apps.dns_agent.store import postgres as store

logger = structlog.get_logger(__name__)

# Active background tasks — kept referenced to prevent GC
_active_tasks: set[asyncio.Task] = set()


def _safe_error(exc: Exception) -> str:
    """
    Render an exception as a safe error string.
    Strips any token-shaped strings (long hex/base64) from the message.
    """
    msg = str(exc)
    # Redact anything that looks like a token (32+ character alphanumeric strings)
    import re
    redacted = re.sub(r'[A-Za-z0-9_\-]{32,}', '[REDACTED]', msg)
    return redacted[:2000]


async def _run_upsert_job(job: DnsChangeJob, session_factory: Callable) -> None:
    """Execute an upsert change job with retries."""
    settings = get_settings()
    from apps.dns_agent.client.vault_client import dns_vault_client_from_env
    vault = dns_vault_client_from_env()

    payload = job.payload
    tenant_id = job.tenant_id
    env = job.env
    zone_name = job.zone_name
    records = payload.get("records", [])

    for attempt in range(1, settings.job_max_attempts + 1):
        try:
            async with session_factory() as session:
                async with session.begin():
                    zone = await store.get_zone_by_name(session, tenant_id, env, zone_name)
                    if not zone:
                        raise RuntimeError(f"Zone '{zone_name}' not found for tenant={tenant_id} env={env}")

                    adapter = await get_adapter(
                        zone.provider, tenant_id, env, vault, job.correlation_id
                    )

                    for rec in records:
                        spec = RecordSpec(
                            record_type=rec["record_type"],
                            name=rec["name"],
                            value=rec["value"],
                            ttl=rec.get("ttl", 300),
                            priority=rec.get("priority"),
                        )
                        provider_rec = await adapter.upsert_record(zone.provider_zone_id, spec)
                        await store.upsert_record(
                            session, zone,
                            record_type=spec.record_type,
                            name=spec.name,
                            value=spec.value,
                            ttl=spec.ttl,
                            priority=spec.priority,
                            tags=rec.get("tags"),
                            provider_record_id=provider_rec.provider_record_id,
                        )

                    await store.update_job_status(session, job, "succeeded")
                    logger.info("dns_job_succeeded", job_id=job.id, operation=job.operation)
                    return

        except Exception as exc:
            safe_msg = _safe_error(exc)
            logger.warning("dns_job_attempt_failed", job_id=job.id, attempt=attempt, error=safe_msg)
            delay = settings.job_base_delay_seconds * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            if attempt < settings.job_max_attempts:
                await asyncio.sleep(delay)

    # All attempts exhausted
    async with session_factory() as session:
        async with session.begin():
            await store.update_job_status(session, job, "failed", last_error=safe_msg)
    logger.error("dns_job_failed", job_id=job.id)


async def _run_delete_job(job: DnsChangeJob, session_factory: Callable) -> None:
    """Execute a delete change job with retries."""
    settings = get_settings()
    from apps.dns_agent.client.vault_client import dns_vault_client_from_env
    vault = dns_vault_client_from_env()

    payload = job.payload
    tenant_id = job.tenant_id
    env = job.env
    zone_name = job.zone_name
    records = payload.get("records", [])
    safe_msg = ""

    for attempt in range(1, settings.job_max_attempts + 1):
        try:
            async with session_factory() as session:
                async with session.begin():
                    zone = await store.get_zone_by_name(session, tenant_id, env, zone_name)
                    if not zone:
                        raise RuntimeError(f"Zone '{zone_name}' not found.")

                    adapter = await get_adapter(zone.provider, tenant_id, env, vault, job.correlation_id)

                    for rec in records:
                        existing = await store.get_record(
                            session, zone.id, rec["record_type"], rec["name"]
                        )
                        if existing and existing.provider_record_id:
                            await adapter.delete_record(zone.provider_zone_id, existing.provider_record_id)
                        await store.delete_record_by_spec(session, zone.id, rec["record_type"], rec["name"])

                    await store.update_job_status(session, job, "succeeded")
                    logger.info("dns_job_succeeded", job_id=job.id, operation="delete")
                    return
        except Exception as exc:
            safe_msg = _safe_error(exc)
            logger.warning("dns_job_attempt_failed", job_id=job.id, attempt=attempt, error=safe_msg)
            delay = settings.job_base_delay_seconds * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            if attempt < settings.job_max_attempts:
                await asyncio.sleep(delay)

    async with session_factory() as session:
        async with session.begin():
            await store.update_job_status(session, job, "failed", last_error=safe_msg)


def dispatch_job(job: DnsChangeJob, session_factory: Callable) -> None:
    """
    Fire-and-forget: dispatch a change job as a background asyncio task.
    The task reference is kept in _active_tasks to prevent GC.
    """
    if job.operation == "upsert":
        coro = _run_upsert_job(job, session_factory)
    elif job.operation == "delete":
        coro = _run_delete_job(job, session_factory)
    else:
        logger.error("dns_job_unknown_operation", operation=job.operation, job_id=job.id)
        return

    task = asyncio.create_task(coro)
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)
    logger.info("dns_job_dispatched", job_id=job.id, operation=job.operation)
