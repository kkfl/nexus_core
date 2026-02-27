"""
Mailbox stats service — uses SSH doveadm commands to fetch quota and unread.

All commands are read-only and run via the existing SSH bridge.
Results are cached with a configurable TTL.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time

import structlog

from apps.email_agent.client import vault
from apps.email_agent.config import config

logger = structlog.get_logger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────────────
_stats_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str) -> dict | None:
    """Return cached value if still fresh, else None."""
    if key in _stats_cache:
        ts, data = _stats_cache[key]
        if time.time() - ts < config.stats_cache_ttl_seconds:
            return data
    return None


def _cache_set(key: str, data: dict) -> None:
    _stats_cache[key] = (time.time(), data)


# ── SSH helpers ──────────────────────────────────────────────────────────────


def _build_ssh():
    """Build paramiko SSH client (synchronous)."""
    import io

    import paramiko

    host = _ssh_creds["host"]
    port = _ssh_creds["port"]
    username = _ssh_creds["username"]
    pem = _ssh_creds["pem"]

    pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=username, pkey=pkey, timeout=10)
    return ssh


# Thread-local creds resolved from vault before thread dispatch
_ssh_creds: dict = {}


async def _resolve_ssh_creds() -> dict:
    """Resolve SSH credentials from vault."""
    return {
        "host": await vault.get_secret("ssh.iredmail.host"),
        "port": int(await vault.get_secret("ssh.iredmail.port")),
        "username": await vault.get_secret("ssh.iredmail.username"),
        "pem": await vault.get_secret("ssh.iredmail.private_key_pem"),
    }


def _run_ssh_cmd(cmd: str) -> str:
    """Run a single SSH command and return stdout (synchronous)."""
    ssh = _build_ssh()
    try:
        _stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
        out = stdout.read().decode().strip()
        return out
    finally:
        ssh.close()


# ── Quota stats via doveadm ──────────────────────────────────────────────────


def _parse_quota(output: str, email: str, quota_mb: int) -> dict:
    """Parse doveadm quota get output.

    Example output:
    user@domain  STORAGE  1234  102400  -  MESSAGE  56  -  -
    """
    used_kb = 0
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Quota"):
            continue
        # Try to extract STORAGE usage in KB
        parts = re.split(r"\s+", line)
        # Format: name  type  value  limit  %
        for i, p in enumerate(parts):
            if p == "STORAGE" and i + 1 < len(parts):
                with contextlib.suppress(ValueError):
                    used_kb = int(parts[i + 1])
                break

    used_mb = round(used_kb / 1024, 1)
    free_mb = max(0, round(quota_mb - used_mb, 1))
    used_pct = round((used_mb / quota_mb * 100) if quota_mb > 0 else 0, 1)
    free_pct = round(100 - used_pct, 1)

    return {
        "email": email,
        "quota_mb": quota_mb,
        "used_mb": used_mb,
        "used_pct": used_pct,
        "free_mb": free_mb,
        "free_pct": free_pct,
    }


def _sync_get_stats(email: str, quota_mb: int) -> dict:
    """Synchronous: get quota + unread + total for a mailbox."""
    # Quota
    quota_out = _run_ssh_cmd(f"sudo doveadm quota get -u '{email}'")
    stats = _parse_quota(quota_out, email, quota_mb)

    # Unread count
    try:
        unread_out = _run_ssh_cmd(
            f"sudo doveadm search -u '{email}' mailbox INBOX UNSEEN 2>/dev/null | wc -l"
        )
        stats["unread_count"] = int(unread_out.strip()) if unread_out.strip().isdigit() else 0
    except Exception:
        stats["unread_count"] = 0

    # Total count
    try:
        total_out = _run_ssh_cmd(
            f"sudo doveadm search -u '{email}' mailbox INBOX ALL 2>/dev/null | wc -l"
        )
        stats["total_count"] = int(total_out.strip()) if total_out.strip().isdigit() else 0
    except Exception:
        stats["total_count"] = 0

    # Last received — check most recent message date
    try:
        last_out = _run_ssh_cmd(
            f"sudo doveadm fetch -u '{email}' 'date.received' mailbox INBOX "
            "SAVEDSINCE 1d 2>/dev/null | head -1"
        )
        if last_out and "date.received" in last_out:
            stats["last_received_at"] = last_out.split(":", 1)[-1].strip()
        else:
            stats["last_received_at"] = None
    except Exception:
        stats["last_received_at"] = None

    return stats


async def get_mailbox_stats(email: str, quota_mb: int = 0) -> dict:
    """Get per-mailbox stats. Returns cached if fresh."""
    cached = _cache_get(f"stats:{email}")
    if cached:
        return cached

    global _ssh_creds
    _ssh_creds = await _resolve_ssh_creds()

    result = await asyncio.to_thread(_sync_get_stats, email, quota_mb)
    _cache_set(f"stats:{email}", result)
    logger.info("mailbox_stats", email=email, used_mb=result.get("used_mb"))
    return result


async def get_bulk_stats(mailboxes: list[dict]) -> list[dict]:
    """Get stats for multiple mailboxes. Uses cache, batches SSH calls."""
    results = []
    for mbox in mailboxes:
        email = mbox.get("email", "")
        quota = mbox.get("quota", 0)
        try:
            stats = await get_mailbox_stats(email, quota)
            results.append(stats)
        except Exception as e:
            logger.warning("bulk_stats_error", email=email, error=str(e)[:100])
            results.append(
                {
                    "email": email,
                    "quota_mb": quota,
                    "used_mb": 0,
                    "used_pct": 0,
                    "free_mb": quota,
                    "free_pct": 100,
                    "unread_count": 0,
                    "total_count": 0,
                    "last_received_at": None,
                }
            )
    return results
