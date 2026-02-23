import uuid

import httpx
import structlog

from apps.storage_agent.config import get_settings
from apps.storage_agent.engine.secrets import get_secret

logger = structlog.get_logger(__name__)


async def dispatch_alert(
    tenant_id: str,
    env: str,
    subject: str,
    body: str,
    channel: str = "telegram",
    correlation_id: str | None = None,
) -> bool:
    """Send an alert to notifications-agent via a POST request."""
    settings = get_settings()
    url = f"{settings.notifications_base_url}/v1/notify"

    headers = {
        "X-Service-ID": settings.service_name,
        "X-Correlation-ID": correlation_id or str(uuid.uuid4()),
    }

    # Needs auth! Fetch the shared system token to notify the platform
    # We use our own key or the automation-agent key
    alias = "storage-agent.automation-agent.key"
    token = await get_secret(alias, tenant_id, env, correlation_id)
    if token:
        headers["X-Agent-Key"] = token

    payload = {
        "tenant_id": tenant_id,
        "env": env,
        "channel": channel,
        "subject": subject,
        "body": body,
        "urgency": "high",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 202):
                logger.info("alert_dispatched", subject=subject, channel=channel)
                return True
            else:
                logger.error(
                    "alert_dispatch_failed", status_code=resp.status_code, text=resp.text[:200]
                )
                return False
    except Exception as e:
        logger.error("alert_dispatch_exception", error=str(e)[:250])
        return False
