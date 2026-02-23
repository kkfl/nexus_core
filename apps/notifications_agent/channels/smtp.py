"""
SMTP email channel using aiosmtplib.
Secrets (from vault):
  smtp.host, smtp.port, smtp.username, smtp.password, smtp.from_address

Sends HTML + plain-text multipart. Never logs credentials.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

from apps.notifications_agent.channels.base import NotificationChannel, SendResult

logger = structlog.get_logger(__name__)


class SmtpChannel(NotificationChannel):
    channel_name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        use_tls: bool = True,
    ) -> None:
        self.__host = host
        self.__port = port
        self.__username = username
        self.__password = password
        self._from_address = from_address
        self._use_tls = use_tls

    def __repr__(self) -> str:
        return f"SmtpChannel(host={self.__host}, from={self._from_address}, pass=[REDACTED])"

    async def send(
        self,
        *,
        subject: str | None,
        body: str,
        destination: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        to_addr = destination
        if not to_addr:
            return SendResult(
                success=False,
                error_code="no_destination",
                error_detail="No recipient email address provided",
            )

        dest_hash = hashlib.sha256(to_addr.encode()).hexdigest()
        msg_id = f"<{uuid.uuid4()}@nexus>"
        subj = subject or "Nexus Notification"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subj
        msg["From"] = self._from_address
        msg["To"] = to_addr
        msg["Message-ID"] = msg_id
        msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S %z")
        if context and (corr_id := context.get("correlation_id")):
            msg["X-Nexus-Correlation-ID"] = corr_id

        msg.attach(MIMEText(body, "plain", "utf-8"))
        html_body = body.replace("\n", "<br>")
        msg.attach(
            MIMEText(
                f"<html><body><pre style='font-family:sans-serif'>{html_body}</pre></body></html>",
                "html",
                "utf-8",
            )
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.__host,
                port=self.__port,
                username=self.__username,
                password=self.__password,
                use_tls=self._use_tls,
                start_tls=not self._use_tls,
            )
            logger.info("smtp_sent", to_hash=dest_hash[:12], msg_id=msg_id)
            return SendResult(success=True, provider_msg_id=msg_id, destination_hash=dest_hash)
        except Exception as exc:
            safe = str(exc).replace(self.__password, "[REDACTED]") if self.__password else str(exc)
            logger.error("smtp_send_failed", error=safe[:200])
            return SendResult(
                success=False,
                destination_hash=dest_hash,
                error_code="smtp_error",
                error_detail=safe[:500],
            )
