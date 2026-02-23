"""
SMS channel via Twilio REST API.
Secrets (from vault):
  sms.twilio.account_sid
  sms.twilio.auth_token
  sms.twilio.from_number

If vault aliases are not configured, returns ChannelNotConfigured gracefully.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

import httpx
import structlog

from apps.notifications_agent.channels.base import NotificationChannel, SendResult

logger = structlog.get_logger(__name__)

_TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class SmsChannel(NotificationChannel):
    channel_name = "sms"

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self.__account_sid = account_sid
        self.__auth_token = auth_token
        self._from_number = from_number

    def __repr__(self) -> str:
        return "SmsChannel(provider=twilio, from=[REDACTED])"

    async def send(self, *, subject: Optional[str], body: str,
                   destination: Optional[str] = None,
                   context: dict | None = None) -> SendResult:
        to_number = destination
        if not to_number:
            return SendResult(success=False, error_code="no_destination",
                              error_detail="No phone number provided")

        dest_hash = hashlib.sha256(to_number.encode()).hexdigest()
        # SMS: no HTML, no subject, max 1600 chars (multi-part SMS handled by Twilio)
        sms_body = body[:1600]
        if subject:
            sms_body = f"[{subject}] {sms_body}"[:1600]

        url = _TWILIO_MESSAGES_URL.format(sid=self.__account_sid)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    auth=(self.__account_sid, self.__auth_token),
                    data={"From": self._from_number, "To": to_number, "Body": sms_body},
                )
            data = resp.json()
            if resp.status_code >= 400:
                err = data.get("message", resp.text[:200])
                # Twilio error messages are safe — no credentials in them
                return SendResult(success=False, destination_hash=dest_hash,
                                  error_code=str(data.get("code", "twilio_error")),
                                  error_detail=err[:500])
            msg_sid = data.get("sid", "")
            logger.info("sms_sent", to_hash=dest_hash[:12], sid=msg_sid)
            return SendResult(success=True, provider_msg_id=msg_sid, destination_hash=dest_hash)
        except Exception as exc:
            safe = re.sub(r'[A-Za-z0-9+/=]{32,}', '[REDACTED]', str(exc))[:500]
            logger.error("sms_send_failed", error=safe)
            return SendResult(success=False, destination_hash=dest_hash,
                              error_code="sms_error", error_detail=safe)


class SmsChannelNotConfigured(NotificationChannel):
    """Returned when SMS vault secrets are not registered."""
    channel_name = "sms"

    async def send(self, *, subject: Optional[str], body: str,
                   destination: Optional[str] = None,
                   context: dict | None = None) -> SendResult:
        logger.warning("sms_channel_not_configured")
        return SendResult(success=False, error_code="channel_not_configured",
                          error_detail="SMS provider (Twilio) credentials not registered in vault",
                          destination_hash="")
