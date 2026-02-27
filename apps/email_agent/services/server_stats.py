"""
Server-level stats — postfix queue depth + summary via SSH.

All commands are read-only.
"""

from __future__ import annotations

import asyncio
import re
import time

import structlog

from apps.email_agent.client import vault

logger = structlog.get_logger(__name__)

# ── Cache ────────────────────────────────────────────────────────────────────
_server_cache: dict[str, tuple[float, dict]] = {}
_SERVER_CACHE_TTL = 30  # seconds


def _cache_get(key: str) -> dict | None:
    if key in _server_cache:
        ts, data = _server_cache[key]
        if time.time() - ts < _SERVER_CACHE_TTL:
            return data
    return None


def _cache_set(key: str, data: dict) -> None:
    _server_cache[key] = (time.time(), data)


# ── SSH ──────────────────────────────────────────────────────────────────────
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


def _sync_get_server_stats() -> dict:
    """Parse postqueue -p for queue summary."""
    ssh = _build_ssh()
    try:
        _stdin, stdout, _stderr = ssh.exec_command(
            "sudo postqueue -p 2>/dev/null | tail -1", timeout=10
        )
        tail = stdout.read().decode().strip()

        # Example: "-- 3 Kbytes in 2 Requests."
        # Or empty queue: "Mail queue is empty"
        stats = {
            "queue_total": 0,
            "deferred": 0,
            "active": 0,
            "hold": 0,
            "corrupt": 0,
        }

        if "empty" in tail.lower():
            return stats

        m = re.search(r"(\d+)\s+Request", tail)
        if m:
            stats["queue_total"] = int(m.group(1))

        # Get deferred count specifically
        _stdin2, stdout2, _stderr2 = ssh.exec_command(
            "sudo find /var/spool/postfix/deferred -type f 2>/dev/null | wc -l",
            timeout=10,
        )
        deferred_out = stdout2.read().decode().strip()
        if deferred_out.isdigit():
            stats["deferred"] = int(deferred_out)

        # Active count
        _stdin3, stdout3, _stderr3 = ssh.exec_command(
            "sudo find /var/spool/postfix/active -type f 2>/dev/null | wc -l",
            timeout=10,
        )
        active_out = stdout3.read().decode().strip()
        if active_out.isdigit():
            stats["active"] = int(active_out)

        return stats
    finally:
        ssh.close()


async def get_server_stats() -> dict:
    """Get server-level postfix queue stats. Cached for 30s."""
    cached = _cache_get("server_stats")
    if cached:
        return cached

    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()

    result = await asyncio.to_thread(_sync_get_server_stats)
    _cache_set("server_stats", result)
    logger.info("server_stats", queue_total=result.get("queue_total"))
    return result
