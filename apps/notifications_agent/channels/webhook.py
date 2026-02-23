"""
Webhook channel — HMAC-SHA256 signed POST to a URL.
Signing secret stored in vault as: webhook.<tenant_id>.signing_secret
Webhook URL is stored in routing_rules.config (non-secret; not a credential).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from apps.notifications_agent.channels.base import NotificationChannel, SendResult

logger = structlog.get_logger(__name__)


def _sign_payload(secret: str, body_bytes: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


class WebhookChannel(NotificationChannel):
    channel_name = "webhook"

    def __init__(self, signing_secret: str) -> None:
        self.__signing_secret = signing_secret

    def __repr__(self) -> str:
        return "WebhookChannel(signing_secret=[REDACTED])"

    async def send(self, *, subject: Optional[str], body: str,
                   destination: Optional[str] = None,
                   context: dict | None = None) -> SendResult:
        url = destination
        if not url:
            return SendResult(success=False, error_code="no_destination",
                              error_detail="No webhook URL configured")

        dest_hash = hashlib.sha256(url.encode()).hexdigest()
        correlation_id = (context or {}).get("correlation_id", "")

        payload = {
            "event": subject or "nexus.notification",
            "body": body,
            "severity": (context or {}).get("severity", "info"),
            "tenant_id": (context or {}).get("tenant_id", ""),
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload_bytes = json.dumps(payload).encode()
        signature = _sign_payload(self.__signing_secret, payload_bytes)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Nexus-Signature": signature,
                        "X-Nexus-Correlation-ID": correlation_id,
                    },
                )
            if resp.status_code >= 400:
                safe_err = resp.text[:300]
                return SendResult(success=False, destination_hash=dest_hash,
                                  error_code=f"http_{resp.status_code}",
                                  error_detail=safe_err)
            logger.info("webhook_sent", url_hash=dest_hash[:12], status=resp.status_code)
            return SendResult(success=True, provider_msg_id=str(resp.status_code),
                              destination_hash=dest_hash)
        except Exception as exc:
            safe = re.sub(r'[A-Za-z0-9+/=]{32,}', '[REDACTED]', str(exc))[:500]
            logger.error("webhook_send_failed", error=safe)
            return SendResult(success=False, destination_hash=dest_hash,
                              error_code="webhook_error", error_detail=safe)
