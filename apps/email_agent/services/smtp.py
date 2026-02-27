"""
SMTP send service — sends email via mx.gsmcall.com:587 STARTTLS.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

from apps.email_agent.client import vault

logger = structlog.get_logger(__name__)


async def _get_smtp_config() -> dict:
    """Resolve SMTP config from vault."""
    return {
        "host": await vault.get_secret("smtp.host"),
        "port": int(await vault.get_secret("smtp.port")),
        "username": await vault.get_secret("smtp.username"),
        "password": await vault.get_secret("smtp.password"),
        "from_address": await vault.get_secret("smtp.from_address"),
    }


async def send_email(
    *,
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict:
    """Send an email. Returns {ok, message_id, error}."""
    cfg = await _get_smtp_config()
    msg_id = f"<{uuid.uuid4()}@nexus>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"]
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Message-ID"] = msg_id
    msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S %z")

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    else:
        html = body_text.replace("\n", "<br>")
        msg.attach(
            MIMEText(
                f"<html><body><pre style='font-family:sans-serif'>{html}</pre></body></html>",
                "html",
                "utf-8",
            )
        )

    all_recipients = list(to) + (cc or []) + (bcc or [])

    try:
        port = cfg["port"]
        use_tls = port == 465
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=port,
            username=cfg["username"],
            password=cfg["password"],
            use_tls=use_tls,
            start_tls=not use_tls,
            validate_certs=False,
            recipients=all_recipients,
            timeout=15,
        )
        dest_hash = hashlib.sha256(",".join(to).encode()).hexdigest()[:12]
        logger.info("smtp_sent", to_hash=dest_hash, msg_id=msg_id)
        return {"ok": True, "message_id": msg_id}
    except Exception as exc:
        safe = str(exc)
        if cfg["password"]:
            safe = safe.replace(cfg["password"], "[REDACTED]")
        logger.error("smtp_send_failed", error=safe[:200])
        return {"ok": False, "message_id": None, "error": safe[:500]}


async def _do_smtp_check(cfg):
    """Actual SMTP check — use aiosmtplib.send-style connect."""
    port = cfg["port"]
    use_tls = port == 465
    # Use the same approach as aiosmtplib.send() which handles STARTTLS correctly
    smtp = aiosmtplib.SMTP(
        hostname=cfg["host"],
        port=port,
        use_tls=use_tls,
        start_tls=not use_tls,
        validate_certs=False,
        timeout=10,
    )
    await smtp.connect()
    await smtp.quit()
    return True, "connected"


async def check_smtp_connectivity() -> tuple[bool, str]:
    """Quick SMTP connectivity test with 10s hard timeout."""
    try:
        cfg = await _get_smtp_config()
        return await asyncio.wait_for(_do_smtp_check(cfg), timeout=10)
    except asyncio.TimeoutError:
        return False, "connection timed out"
    except Exception as e:
        return False, str(e)[:200]

