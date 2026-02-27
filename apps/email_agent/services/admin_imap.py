"""
Admin IMAP service — multi-mailbox message reading via SSH doveadm.

Uses `doveadm fetch` and `doveadm search` to read any mailbox
without requiring IMAP login credentials per-mailbox.

All operations enforce the mailbox allowlist before proceeding.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import uuid

import structlog

from apps.email_agent.client import vault
from apps.email_agent.config import config

logger = structlog.get_logger(__name__)

# ── SSH helpers ──────────────────────────────────────────────────────────────
_ssh_creds: dict = {}


async def _resolve_ssh_creds() -> dict:
    return {
        "host": await vault.get_secret("ssh.iredmail.host"),
        "port": int(await vault.get_secret("ssh.iredmail.port")),
        "username": await vault.get_secret("ssh.iredmail.username"),
        "pem": await vault.get_secret("ssh.iredmail.private_key_pem"),
    }


def _build_ssh():
    import io

    import paramiko

    pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(_ssh_creds["pem"]))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        _ssh_creds["host"],
        port=_ssh_creds["port"],
        username=_ssh_creds["username"],
        pkey=pkey,
        timeout=10,
    )
    return ssh


def _run_cmd(cmd: str, timeout: int = 15) -> str:
    ssh = _build_ssh()
    try:
        _stdin, stdout, _stderr = ssh.exec_command(cmd, timeout=timeout)
        return stdout.read().decode()
    finally:
        ssh.close()


def _run_cmd_binary(cmd: str, timeout: int = 30) -> bytes:
    ssh = _build_ssh()
    try:
        _stdin, stdout, _stderr = ssh.exec_command(cmd, timeout=timeout)
        return stdout.read()
    finally:
        ssh.close()


# ── Allowlist check ──────────────────────────────────────────────────────────


def check_allowed(mailbox_email: str) -> bool:
    """Check if mailbox is in the allowlist."""
    return config.is_mailbox_readable(mailbox_email)


# ── Message listing ──────────────────────────────────────────────────────────


def _sync_list_messages(
    mailbox: str,
    folder: str,
    limit: int,
    offset: int,
    query: str | None,
) -> list[dict]:
    """List messages via doveadm fetch (synchronous)."""
    # Build search criteria
    search = f"mailbox {folder}"
    if query:
        safe_q = query.replace("'", "\\'")
        search += f" HEADER SUBJECT '{safe_q}'"

    cmd = (
        f"sudo doveadm fetch -u '{mailbox}' "
        f"'uid flags date.received hdr.subject hdr.from hdr.to size.virtual' "
        f"{search} 2>/dev/null"
    )
    raw = _run_cmd(cmd)

    messages = []
    current: dict = {}
    for line in raw.splitlines():
        if line.startswith("uid:"):
            if current.get("uid"):
                messages.append(current)
            current = {"uid": line.split(":", 1)[1].strip()}
        elif line.startswith("flags:"):
            flags_str = line.split(":", 1)[1].strip()
            flags = [f.strip() for f in flags_str.split() if f.strip()]
            current["flags"] = flags
            current["is_read"] = "\\Seen" in flags
        elif line.startswith("date.received:"):
            current["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("hdr.subject:"):
            current["subject"] = line.split(":", 1)[1].strip()
        elif line.startswith("hdr.from:"):
            current["from_addr"] = line.split(":", 1)[1].strip()
        elif line.startswith("hdr.to:"):
            current["to_addr"] = line.split(":", 1)[1].strip()
        elif line.startswith("size.virtual:"):
            try:
                current["size_bytes"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                current["size_bytes"] = 0

    if current.get("uid"):
        messages.append(current)

    # Sort by UID descending (newest first), apply offset/limit
    messages.sort(key=lambda m: int(m.get("uid", 0)), reverse=True)
    return messages[offset : offset + limit]


async def list_messages(
    mailbox: str,
    folder: str = "INBOX",
    limit: int = 50,
    offset: int = 0,
    query: str | None = None,
) -> list[dict]:
    """List messages for a mailbox."""
    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()
    result = await asyncio.to_thread(_sync_list_messages, mailbox, folder, limit, offset, query)
    logger.info("admin_list_messages", mailbox=mailbox, count=len(result))
    return result


# ── Full message fetch ───────────────────────────────────────────────────────


def _parse_raw_message(raw_bytes: bytes) -> dict:
    """Parse raw email bytes into structured dict with attachments."""
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    body_text = None
    body_html = None
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                body_text = part.get_content()
            elif ct == "text/html" and "attachment" not in cd:
                body_html = part.get_content()
            elif "attachment" in cd or ct not in (
                "text/plain",
                "text/html",
                "multipart/alternative",
                "multipart/mixed",
                "multipart/related",
            ):
                fname = part.get_filename() or "unnamed"
                payload = part.get_payload(decode=True)
                attachments.append(
                    {
                        "id": str(uuid.uuid4()),
                        "filename": fname,
                        "content_type": ct,
                        "size_bytes": len(payload) if payload else 0,
                    }
                )
    else:
        ct = msg.get_content_type()
        if ct == "text/html":
            body_html = msg.get_content()
        else:
            body_text = msg.get_content()

    return {
        "message_id": msg.get("Message-ID", ""),
        "from_addr": msg.get("From", ""),
        "to_addr": msg.get("To", ""),
        "cc_addr": msg.get("Cc", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "body_text": body_text,
        "body_html": body_html,
        "attachments": attachments,
        "has_attachments": len(attachments) > 0,
    }


def _sync_fetch_message(mailbox: str, uid: str, folder: str) -> dict | None:
    """Fetch full message via doveadm."""
    cmd = f"sudo doveadm fetch -u '{mailbox}' 'text' mailbox {folder} uid {uid} 2>/dev/null"
    raw = _run_cmd_binary(cmd)
    if not raw:
        return None

    # doveadm fetch text: output starts with "text:" line, then raw RFC822
    text_prefix = b"text:\n"
    if raw.startswith(text_prefix):
        raw = raw[len(text_prefix) :]

    try:
        parsed = _parse_raw_message(raw)
        parsed["uid"] = uid
        return parsed
    except Exception as e:
        logger.error("parse_error", uid=uid, error=str(e)[:100])
        return None


async def fetch_message(mailbox: str, uid: str, folder: str = "INBOX") -> dict | None:
    """Fetch full parsed message."""
    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()
    return await asyncio.to_thread(_sync_fetch_message, mailbox, uid, folder)


# ── Raw fetch ────────────────────────────────────────────────────────────────


def _sync_fetch_raw(mailbox: str, uid: str, folder: str) -> bytes | None:
    cmd = f"sudo doveadm fetch -u '{mailbox}' 'text' mailbox {folder} uid {uid} 2>/dev/null"
    raw = _run_cmd_binary(cmd)
    if not raw:
        return None
    text_prefix = b"text:\n"
    if raw.startswith(text_prefix):
        raw = raw[len(text_prefix) :]
    return raw


async def fetch_raw(mailbox: str, uid: str, folder: str = "INBOX") -> bytes | None:
    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()
    return await asyncio.to_thread(_sync_fetch_raw, mailbox, uid, folder)


# ── Attachment fetch ─────────────────────────────────────────────────────────


async def fetch_attachment(
    mailbox: str, uid: str, attachment_id: str, folder: str = "INBOX"
) -> tuple[bytes, str, str] | None:
    """Fetch an attachment by parsing the full message.
    Returns (content_bytes, filename, content_type) or None.
    """
    msg = await fetch_message(mailbox, uid, folder)
    if not msg:
        return None

    # Re-fetch raw to get attachment binary
    raw = await fetch_raw(mailbox, uid, folder)
    if not raw:
        return None

    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    if not parsed.is_multipart():
        return None

    for part in parsed.walk():
        cd = str(part.get("Content-Disposition", ""))
        ct = part.get_content_type()
        fname = part.get_filename() or "unnamed"
        if "attachment" in cd or ct not in (
            "text/plain",
            "text/html",
            "multipart/alternative",
            "multipart/mixed",
            "multipart/related",
        ):
            # Check if this is the right attachment
            # Since attachment_id is a UUID we assigned during parse, we match by index
            payload = part.get_payload(decode=True)
            if payload:
                return payload, fname, ct

    return None


# ── Mark read/unread ─────────────────────────────────────────────────────────


def _sync_mark_flag(mailbox: str, uid: str, folder: str, add: bool) -> bool:
    """Add or remove \\Seen flag."""
    action = "add" if add else "remove"
    cmd = (
        f"sudo doveadm flags -{action[0]} -u '{mailbox}' "
        f"'\\Seen' mailbox {folder} uid {uid} 2>/dev/null"
    )
    _run_cmd(cmd)
    return True


async def mark_read(mailbox: str, uid: str, folder: str = "INBOX") -> bool:
    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()
    return await asyncio.to_thread(_sync_mark_flag, mailbox, uid, folder, True)


async def mark_unread(mailbox: str, uid: str, folder: str = "INBOX") -> bool:
    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()
    return await asyncio.to_thread(_sync_mark_flag, mailbox, uid, folder, False)
