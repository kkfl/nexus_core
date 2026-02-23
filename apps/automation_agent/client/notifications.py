from typing import Optional, Dict, Any
import httpx
import structlog
from apps.automation_agent.client.registry import resolve_agent
from apps.automation_agent.config import config

logger = structlog.get_logger(__name__)

async def send_notification(
    tenant_id: str,
    env: str,
    severity: str,
    template_id: str,
    context: Dict[str, Any],
    correlation_id: str,
    idempotency_key: str
) -> bool:
    """
    Sends a notification via notifications-agent.
    """
    try:
        agent = await resolve_agent("notifications-agent", tenant_id, env)
    except RuntimeError as ex:
        logger.error("notifications_agent_resolution_failed", error=str(ex))
        return False

    url = f"{agent.base_url}/v1/notify"
    
    # We use a specific key if defined, else fallback
    notify_key = config.automation_agent_keys.get("notify", "automation-notify-key-change-me")
    
    headers = {
        "X-Service-ID": "automation-agent",
        "X-Agent-Key": notify_key,
        "X-Correlation-ID": correlation_id
    }
    
    payload = {
        "tenant_id": tenant_id,
        "env": env,
        "severity": severity,
        "template_id": template_id,
        "context": context,
        "idempotency_key": idempotency_key,
        "channels": ["telegram"] # Hardcoded to telegram for MVP safety alerts
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error("notification_send_failed", template=template_id, error=str(e))
        return False
