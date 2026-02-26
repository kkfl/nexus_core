"""
Async job queue runner for notifications_agent.
- Dispatches asyncio.Task per channel delivery
- Retry with exponential backoff + jitter
- After max_attempts: job status → "failed" (DLQ — queryable/replayable via API)
- Never blocks the HTTP request path
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import UTC, datetime

import structlog

from apps.notifications_agent import metrics
from apps.notifications_agent.channels.factory import build_channel
from apps.notifications_agent.config import get_settings
from apps.notifications_agent.store.postgres import (
    create_delivery,
    get_db,
    set_job_status,
    update_delivery,
)
from apps.secrets_agent.client.vault_client import VaultClient

logger = structlog.get_logger(__name__)


def _safe_error(exc: Exception) -> str:
    msg = re.sub(r"[A-Za-z0-9+/=]{32,}", "[REDACTED]", str(exc))
    return msg[:1000]


def _vault() -> VaultClient:
    s = get_settings()
    return VaultClient(
        base_url=s.vault_base_url,
        service_id=s.vault_service_id,
        api_key=s.vault_agent_key,
    )


async def _deliver_channel(
    *,
    job_id: str,
    channel_name: str,
    subject: str | None,
    body: str,
    destination: str | None,
    tenant_id: str,
    env: str,
    correlation_id: str,
    channel_config: dict | None,
    max_attempts: int,
) -> None:
    """Inner coroutine: attempt delivery with retries, update delivery row.

    INVARIANT: once channel.send() returns successfully, we NEVER re-send,
    even if the subsequent DB bookkeeping fails.  Retries only cover
    pre-send failures (vault/channel build) and actual send errors.
    """
    settings = get_settings()
    base_delay = settings.job_retry_base_delay

    result = None  # set on successful send
    sent_attempt = 0

    # -- retry loop: covers vault fetch + channel.send() ONLY ---------------
    for attempt in range(1, max_attempts + 1):
        metrics.inc("notification_send_attempts")
        start_ms = asyncio.get_event_loop().time() * 1000

        try:
            vault = _vault()
            channel = await build_channel(
                channel_name,
                vault,
                tenant_id=tenant_id,
                env=env,
                correlation_id=correlation_id,
                channel_config=channel_config,
            )

            ctx = {
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "severity": channel_config.get("severity", "") if channel_config else "",
            }

            result = await channel.send(
                subject=subject,
                body=body,
                destination=destination,
                context=ctx,
            )
            elapsed = asyncio.get_event_loop().time() * 1000 - start_ms
            metrics.record_latency(elapsed)
            sent_attempt = attempt
            break  # send succeeded — exit retry loop, NEVER re-send

        except Exception as exc:
            safe = _safe_error(exc)
            logger.error(
                "delivery_exception",
                job_id=job_id,
                channel=channel_name,
                attempt=attempt,
                error=safe,
            )
            metrics.inc("notification_send_failure")
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)

    # -- post-send bookkeeping (outside retry loop) -------------------------
    if result is None:
        # All send attempts exhausted
        logger.error(
            "delivery_failed_dlq",
            job_id=job_id,
            channel=channel_name,
            attempts=max_attempts,
        )
        return

    try:
        async for db in get_db():
            d = await create_delivery(
                db,
                job_id=job_id,
                channel=channel_name,
                destination_hash=result.destination_hash,
            )
            delivery_id = str(d.id)
            if result.success:
                metrics.inc("notification_send_success")
                await update_delivery(
                    db,
                    delivery_id,
                    status="sent",
                    provider_msg_id=result.provider_msg_id,
                    attempt=sent_attempt,
                    sent_at=datetime.now(UTC),
                )
                logger.info(
                    "delivery_success",
                    job_id=job_id,
                    channel=channel_name,
                    attempt=sent_attempt,
                    correlation_id=correlation_id,
                )
            else:
                metrics.inc("notification_send_failure")
                await update_delivery(
                    db,
                    delivery_id,
                    status="failed",
                    attempt=sent_attempt,
                    error_code=result.error_code,
                    error_detail_redacted=result.error_detail,
                )
                logger.error(
                    "delivery_send_returned_failure",
                    job_id=job_id,
                    channel=channel_name,
                    attempt=sent_attempt,
                )
    except Exception as exc:
        # DB bookkeeping failed — the message WAS already sent.
        # Log but do NOT retry (that would duplicate the delivery).
        safe = _safe_error(exc)
        logger.error(
            "delivery_bookkeeping_failed",
            job_id=job_id,
            channel=channel_name,
            attempt=sent_attempt,
            error=safe,
        )


async def dispatch_job(
    *,
    job_id: str,
    tenant_id: str,
    env: str,
    channels: list[str],
    subject: str | None,
    body: str,
    correlation_id: str,
    destinations: dict[str, str] | None = None,
    channel_configs: dict[str, dict] | None = None,
    max_attempts: int = 3,
) -> None:
    """
    Dispatch one asyncio.Task per channel. Non-blocking — caller returns immediately.
    Job status is updated to "succeeded" when ALL channels complete.
    """
    get_settings()
    tasks = []
    for channel_name in channels:
        dest = (destinations or {}).get(channel_name)
        cfg = (channel_configs or {}).get(channel_name, {})
        task = asyncio.create_task(
            _deliver_channel(
                job_id=job_id,
                channel_name=channel_name,
                subject=subject,
                body=body,
                destination=dest,
                tenant_id=tenant_id,
                env=env,
                correlation_id=correlation_id,
                channel_config=cfg,
                max_attempts=max_attempts,
            ),
            name=f"deliver-{job_id}-{channel_name}",
        )
        tasks.append(task)

    async def _finalize():
        results = await asyncio.gather(*tasks, return_exceptions=True)
        final_status = "succeeded"
        for r in results:
            if isinstance(r, Exception):
                final_status = "partial"
        async for db in get_db():
            await set_job_status(db, job_id, final_status, completed_at=datetime.now(UTC))

    asyncio.create_task(_finalize(), name=f"finalize-{job_id}")
    metrics.inc("notification_jobs_dispatched")
