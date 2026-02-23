"""
Notifications client for pbx_agent.
Sends alerts via notifications-agent (non-blocking).
"""

import httpx
import structlog

from apps.pbx_agent.config import config

logger = structlog.get_logger(__name__)


async def send_alert(
    tenant_id: str,
    env: str,
    severity: str,
    subject: str,
    body: str,
    correlation_id: str = "",
) -> None:
    """Fire-and-forget: send a notification via notifications-agent."""
    url = f"{config.notifications_base_url}/v1/notify"
    headers = {
        "X-Service-ID": "pbx-agent",
        "X-Agent-Key": config.pbx_notif_agent_key,
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }
    payload = {
        "tenant_id": tenant_id,
        "env": env,
        "severity": severity,
        "template_id": "generic",
        "context": {"subject": subject, "body": body},
        "idempotency_key": f"pbx-alert-{correlation_id}",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code not in (200, 201, 202):
            logger.warning("notification_failed", status=r.status_code)
    except Exception as e:
        logger.warning("notification_error", error=type(e).__name__)
