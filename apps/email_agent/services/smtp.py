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


async def _save_to_sent_folder(from_address: str, raw_message: str) -> None:
    """Save a copy of the sent email to the sender's IMAP Sent folder.

    Connects directly to the mail server's IMAP SSL port (993) and APPENDs
    the message to the Sent folder.  Best-effort — failures are logged but
    do not block sending.
    """
    try:
        import imaplib

        # IMAP host is the same as the SMTP relay host
        imap_host = await vault.get_secret("smtp.host")
        imap_user = await vault.get_secret("smtp.username")

        # Try dedicated IMAP password first, fall back to SMTP password
        try:
            imap_pass = await vault.get_secret("imap.password")
        except Exception:
            imap_pass = await vault.get_secret("smtp.password")

        def _do_append():
            imap = imaplib.IMAP4_SSL(imap_host, 993)
            typ, _ = imap.login(imap_user, imap_pass)
            if typ != "OK":
                logger.warning("imap_login_failed")
                imap.logout()
                return False

            msg_bytes = raw_message.encode("utf-8")
            typ, data = imap.append("Sent", "\\Seen", None, msg_bytes)
            imap.logout()

            if typ == "OK":
                return True
            logger.warning("imap_append_failed", resp=str(data)[:200])
            return False

        saved = await asyncio.to_thread(_do_append)
        if saved:
            logger.info("sent_folder_saved", method="imap_direct")
        else:
            logger.warning("sent_folder_save_failed", method="imap_direct")
    except Exception as exc:
        logger.warning("sent_folder_save_failed", error=str(exc)[:200])

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
        await _save_to_sent_folder(cfg["from_address"], msg.as_string())
        return {"ok": True, "message_id": msg_id}
    except Exception as exc:
        safe = str(exc)
        if cfg["password"]:
            safe = safe.replace(cfg["password"], "[REDACTED]")
        logger.warning("smtp_direct_failed_trying_bridge", error=safe[:200])

    # ── Fallback: send via SSH bridge's sendmail ──────────────────────
    try:
        from apps.email_agent.client import vault as _vault
        from apps.email_agent.client.ssh_bridge import _build_ssh_client

        host = await _vault.get_secret("ssh.iredmail.host")
        port = int(await _vault.get_secret("ssh.iredmail.port"))
        username = await _vault.get_secret("ssh.iredmail.username")
        pem = await _vault.get_secret("ssh.iredmail.private_key_pem")

        raw_msg = msg.as_string()
        recip_str = " ".join(all_recipients)

        def _send_via_bridge():
            ssh = _build_ssh_client(host, port, username, pem)
            try:
                stdin, stdout, stderr = ssh.exec_command(
                    f"sendmail -t {recip_str}", timeout=30,
                )
                stdin.write(raw_msg)
                stdin.channel.shutdown_write()
                exit_code = stdout.channel.recv_exit_status()
                err = stderr.read().decode().strip()
                if exit_code != 0:
                    return {"ok": False, "message_id": None, "error": f"sendmail exit {exit_code}: {err[:200]}"}
                return {"ok": True, "message_id": msg_id}
            finally:
                ssh.close()

        result = await asyncio.to_thread(_send_via_bridge)
        if result["ok"]:
            dest_hash = hashlib.sha256(",".join(to).encode()).hexdigest()[:12]
            logger.info("smtp_sent_via_bridge", to_hash=dest_hash, msg_id=msg_id)
            await _save_to_sent_folder(cfg["from_address"], msg.as_string())
        else:
            logger.error("smtp_bridge_send_failed", error=result.get("error", "")[:200])
        return result
    except Exception as bridge_exc:
        logger.error("smtp_bridge_fallback_failed", error=str(bridge_exc)[:200])
        return {"ok": False, "message_id": None, "error": str(bridge_exc)[:500]}


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
    except TimeoutError:
        return False, "connection timed out"
    except Exception as e:
        return False, str(e)[:200]
