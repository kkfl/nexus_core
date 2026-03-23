"""
Nexus action notifications — Telegram + Event Bus.

Every significant user action (DNS, PBX, backup, secrets) goes through here.
This module:
  1. Sends a Telegram message via the notifications-agent
  2. Publishes a NexusEvent to the Redis event bus (System Activity Log)

All calls are fire-and-forget — failures are logged but never block the caller.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import structlog

logger = structlog.get_logger(__name__)

# Lazy singletons — initialized on first use
_notif_client = None
_event_bus = None


def _get_notif_client():
    global _notif_client
    if _notif_client is None:
        from apps.notifications_agent.client.notifications_client import NotificationsClient

        base_url = os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008")
        api_key = os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me")
        _notif_client = NotificationsClient(
            base_url=base_url,
            service_id="nexus-api",
            api_key=api_key,
            timeout=5.0,
        )
    return _notif_client


def _get_event_bus():
    global _event_bus
    if _event_bus is None:
        from packages.shared.events.transport import EventBus

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _event_bus = EventBus.from_url(redis_url)
    return _event_bus


async def notify_action(
    *,
    action: str,
    subject: str,
    body: str,
    event_type: str,
    severity: str = "info",
    actor_type: str = "user",
    actor_id: str = "admin",
    payload: dict | None = None,
    tenant_id: str = "nexus",
    env: str = "prod",
) -> None:
    """
    Fire-and-forget notification for a user action.

    Parameters:
        action:      Short label, e.g. "dns.record.created"
        subject:     Telegram message subject (bold header)
        body:        Telegram message body (detail text)
        event_type:  Event bus event type, e.g. "nexus.dns.record.created"
        severity:    info | warn | error | critical
        actor_type:  user | service | system
        actor_id:    Who did it (email or service name)
        payload:     Extra data for the event bus payload
        tenant_id:   Tenant
        env:         Environment
    """
    correlation_id = str(uuid.uuid4())

    # Run both in parallel, catch all exceptions
    await asyncio.gather(
        _send_telegram(subject, body, severity, tenant_id, env, correlation_id),
        _publish_event(
            event_type,
            subject,
            body,
            severity,
            actor_type,
            actor_id,
            payload or {},
            tenant_id,
            correlation_id,
        ),
        return_exceptions=True,
    )


async def _send_telegram(
    subject: str,
    body: str,
    severity: str,
    tenant_id: str,
    env: str,
    correlation_id: str,
) -> None:
    """Send Telegram notification via notifications-agent. Never raises."""
    try:
        client = _get_notif_client()
        await client.notify(
            tenant_id=tenant_id,
            env=env,
            severity=severity,
            channels=["telegram"],
            subject=subject,
            body=body,
            idempotency_key=f"action:{correlation_id}",
            correlation_id=correlation_id,
        )
    except Exception as exc:
        logger.warning("telegram_notification_failed", error=str(exc)[:200])


async def _publish_event(
    event_type: str,
    subject: str,
    body: str,
    severity: str,
    actor_type: str,
    actor_id: str,
    payload: dict,
    tenant_id: str,
    correlation_id: str,
) -> None:
    """Publish to Redis event bus AND persist to Postgres for the System Activity Log. Never raises."""
    try:
        from packages.shared.events.schema import EventActor, NexusEvent

        event = NexusEvent(
            event_type=event_type,
            produced_by="nexus-api",
            correlation_id=correlation_id,
            actor=EventActor(type=actor_type, id=actor_id),
            tenant_id=tenant_id,
            severity=severity,
            payload={
                "summary": subject,
                "detail": body,
                **payload,
            },
        )

        # 1. Publish to Redis
        bus = _get_event_bus()
        stream_id = await bus.publish(event)

        # 2. Persist to Postgres (dashboard reads from bus_events table)
        try:
            from packages.shared.db import AsyncSessionLocal
            from packages.shared.events.store import persist_event

            async with AsyncSessionLocal() as db:
                await persist_event(db, event, stream_id=stream_id)
                await db.commit()
        except Exception as exc:
            logger.warning("event_persist_failed", error=str(exc)[:200])

    except Exception as exc:
        logger.warning("event_bus_publish_failed", error=str(exc)[:200])
