"""
IMAP read/search service — connects to mx.gsmcall.com:993 TLS.

All synchronous imaplib calls are wrapped in asyncio.to_thread()
to avoid blocking the uvicorn event loop.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import ssl
import uuid
from imaplib import IMAP4_SSL

import structlog

from apps.email_agent.client import vault

logger = structlog.get_logger(__name__)


async def _get_imap_config() -> dict:
    """Resolve IMAP config from vault."""
    return {
        "host": await vault.get_secret("email.imap.host"),
        "port": int(await vault.get_secret("email.imap.port")),
        "username": await vault.get_secret("email.imap.username"),
        "password": await vault.get_secret("email.imap.password"),
    }


def _connect_imap(cfg: dict) -> IMAP4_SSL:
    """Open an IMAP4_SSL connection (synchronous)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = IMAP4_SSL(cfg["host"], cfg["port"], ssl_context=ctx, timeout=10)
    conn.login(cfg["username"], cfg["password"])
    return conn


def _parse_message(raw_bytes: bytes) -> dict:
    """Parse raw email bytes into a structured dict."""
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
        "attachment_count": len(attachments),
    }


def _sync_search(cfg, query, since, limit, folder):
    """Synchronous IMAP search (runs in thread)."""
    conn = _connect_imap(cfg)
    try:
        conn.select(folder, readonly=True)
        criteria = []
        if query:
            criteria.append(f'SUBJECT "{query}"')
        if since:
            criteria.append(f'SINCE "{since}"')
        if not criteria:
            criteria.append("ALL")

        search_str = " ".join(criteria)
        status, data = conn.search(None, search_str)
        if status != "OK":
            return []

        msg_ids = data[0].split()
        msg_ids = msg_ids[-limit:][::-1]

        results = []
        for mid in msg_ids:
            status, msg_data = conn.fetch(mid, "(RFC822.HEADER)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            results.append(
                {
                    "id": mid.decode(),
                    "message_id": msg.get("Message-ID", ""),
                    "from_addr": msg.get("From", ""),
                    "to_addr": msg.get("To", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "flags": "",
                    "attachment_count": 0,
                }
            )
        return results
    finally:
        conn.logout()


async def search_inbox(
    query: str | None = None,
    since: str | None = None,
    limit: int = 50,
    folder: str = "INBOX",
) -> list[dict]:
    """Search IMAP inbox. Returns list of message summaries."""
    cfg = await _get_imap_config()
    results = await asyncio.to_thread(_sync_search, cfg, query, since, limit, folder)
    logger.info("imap_search", folder=folder, results=len(results))
    return results


def _sync_fetch(cfg, msg_uid, folder):
    """Synchronous IMAP fetch (runs in thread)."""
    conn = _connect_imap(cfg)
    try:
        conn.select(folder, readonly=True)
        status, data = conn.fetch(msg_uid.encode(), "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return None
        raw = data[0][1]
        parsed = _parse_message(raw)
        parsed["id"] = msg_uid
        return parsed
    finally:
        conn.logout()


async def fetch_message(msg_uid: str, folder: str = "INBOX") -> dict | None:
    """Fetch a full message by sequence number."""
    cfg = await _get_imap_config()
    return await asyncio.to_thread(_sync_fetch, cfg, msg_uid, folder)


def _sync_fetch_raw(cfg, msg_uid, folder):
    """Synchronous raw fetch (runs in thread)."""
    conn = _connect_imap(cfg)
    try:
        conn.select(folder, readonly=True)
        status, data = conn.fetch(msg_uid.encode(), "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return None
        return data[0][1]
    finally:
        conn.logout()


async def fetch_raw(msg_uid: str, folder: str = "INBOX") -> bytes | None:
    """Fetch raw RFC822 bytes."""
    cfg = await _get_imap_config()
    return await asyncio.to_thread(_sync_fetch_raw, cfg, msg_uid, folder)


def _sync_imap_check(cfg):
    """Synchronous connectivity check (runs in thread)."""
    conn = _connect_imap(cfg)
    conn.select("INBOX", readonly=True)
    conn.logout()
    return True, "connected"


async def check_imap_connectivity() -> tuple[bool, str]:
    """Quick IMAP connectivity test."""
    try:
        cfg = await _get_imap_config()
        return await asyncio.to_thread(_sync_imap_check, cfg)
    except Exception as e:
        return False, str(e)[:200]
