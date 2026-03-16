"""
Nexus Alerts — fire-and-forget Telegram notifications for critical actions.

Shared across all Nexus agents (nexus-api, server-agent, email-agent, dns-agent).
Uses NotificationsClient → notifications-agent → Telegram Bot.
Non-blocking, fail-silent — never raises exceptions or blocks API responses.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)

# ── Singleton ────────────────────────────────────────────────────────────────

_client = None
_init_attempted = False


def _get_client():
    global _client, _init_attempted
    if _client is not None:
        return _client
    if _init_attempted:
        return None
    _init_attempted = True

    base_url = os.environ.get("NOTIFICATIONS_BASE_URL", "")
    agent_key = os.environ.get("NEXUS_NOTIF_AGENT_KEY", "")
    if not base_url or not agent_key:
        logger.warning("nexus_alerts_disabled", reason="NOTIFICATIONS_BASE_URL or NEXUS_NOTIF_AGENT_KEY not set")
        return None
    try:
        from apps.notifications_agent.client.notifications_client import NotificationsClient
    except ImportError:
        logger.warning("nexus_alerts_disabled", reason="notifications_agent not available in this container")
        return None
    _client = NotificationsClient(
        base_url=base_url,
        service_id=os.environ.get("NEXUS_NOTIF_SERVICE_ID", "nexus"),
        api_key=agent_key,
    )
    logger.info("nexus_alerts_enabled", base_url=base_url)
    return _client


# ── Emoji + severity map ─────────────────────────────────────────────────────

_ACTION_META: dict[str, dict] = {
    # ── Security (nexus-api) ──────────────────────────────────────────────
    "user_create":          {"emoji": "🆕", "label": "User Created",            "severity": "warn"},
    "user_update":          {"emoji": "✏️",  "label": "User Updated",            "severity": "warn"},
    "user_password_reset":  {"emoji": "🔑", "label": "Password Reset",          "severity": "critical"},
    "api_key_create":       {"emoji": "🔐", "label": "API Key Created",         "severity": "warn"},
    "api_key_rotate":       {"emoji": "🔄", "label": "API Key Rotated",         "severity": "warn"},
    "api_key_toggle":       {"emoji": "⏸️",  "label": "API Key Toggled",         "severity": "info"},
    "api_key_delete":       {"emoji": "🗑️",  "label": "API Key Deleted",         "severity": "warn"},
    "ip_allowlist_add":     {"emoji": "🛡️",  "label": "IP Allowlist Added",      "severity": "critical"},
    "ip_allowlist_toggle":  {"emoji": "⏸️",  "label": "IP Allowlist Toggled",     "severity": "warn"},
    "ip_allowlist_remove":  {"emoji": "❌", "label": "IP Allowlist Removed",     "severity": "critical"},

    # ── Infrastructure (server-agent) ─────────────────────────────────────
    "server_create":        {"emoji": "🖥️",  "label": "Server Created",          "severity": "warn"},
    "server_delete":        {"emoji": "💀", "label": "Server Deleted",          "severity": "critical"},
    "server_start":         {"emoji": "▶️",  "label": "Server Started",          "severity": "info"},
    "server_stop":          {"emoji": "⏹️",  "label": "Server Stopped",          "severity": "warn"},
    "server_reboot":        {"emoji": "🔁", "label": "Server Rebooted",         "severity": "info"},
    "server_rebuild":       {"emoji": "🔨", "label": "Server Rebuilt",          "severity": "critical"},
    "host_create":          {"emoji": "🏗️",  "label": "Host Registered",         "severity": "warn"},
    "host_delete":          {"emoji": "🏚️",  "label": "Host Removed",            "severity": "critical"},

    # ── Email (email-agent) ───────────────────────────────────────────────
    "mailbox_create":       {"emoji": "📬", "label": "Mailbox Created",         "severity": "warn"},
    "mailbox_disable":      {"emoji": "🚫", "label": "Mailbox Disabled",        "severity": "warn"},
    "mailbox_password":     {"emoji": "🔑", "label": "Mailbox Password Reset",  "severity": "critical"},
    "alias_add":            {"emoji": "📎", "label": "Email Alias Added",       "severity": "info"},

    # ── DNS (dns-agent) ───────────────────────────────────────────────────
    "dns_zone_create":      {"emoji": "🌐", "label": "DNS Zone Created",        "severity": "warn"},
    "dns_zone_delete":      {"emoji": "🗑️",  "label": "DNS Zone Removed",        "severity": "critical"},
    "dns_zone_import":      {"emoji": "📥", "label": "DNS Zones Imported",      "severity": "info"},
    "dns_record_upsert":    {"emoji": "📝", "label": "DNS Records Updated",     "severity": "info"},
    "dns_record_delete":    {"emoji": "❌", "label": "DNS Records Deleted",     "severity": "warn"},

    # ── Heartbeat Monitor ─────────────────────────────────────────────────
    "agent_heartbeat_stale": {"emoji": "💔", "label": "Agent Heartbeat Lost",    "severity": "critical"},
}


# ── Public API ───────────────────────────────────────────────────────────────


def send_alert(
    action: str,
    actor: str,
    details: str,
    *,
    severity: str | None = None,
) -> None:
    """
    Fire-and-forget a Telegram alert.
    Schedules the async work on the running event loop — never blocks.

    Args:
        action:   Key from _ACTION_META (e.g. "server_create")
        actor:    Who triggered the action (email, service_id, etc.)
        details:  Human-readable description
        severity: Override severity (default: from _ACTION_META)
    """
    client = _get_client()
    if not client:
        return

    meta = _ACTION_META.get(action, {"emoji": "⚠️", "label": action, "severity": "warn"})
    sev = severity or meta["severity"]

    subject = f"{meta['emoji']} {meta['label']}"
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    body = (
        f"{details}\n"
        f"Actor: {actor}\n"
        f"Time: {timestamp}"
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(client, subject, body, sev, action))
    except RuntimeError:
        logger.debug("nexus_alert_no_loop", action=action)


# Backwards-compatible alias for nexus_api security_alerts.py
send_security_alert = send_alert


async def _send(
    client,
    subject: str,
    body: str,
    severity: str,
    action: str,
) -> None:
    """Async helper — sends the notification, logs if it fails."""
    try:
        result = await client.notify(
            tenant_id="nexus",
            env="prod",
            severity=severity,
            channels=["telegram"],
            subject=subject,
            body=body,
            idempotency_key=f"alert:{action}:{uuid.uuid4()}",
        )
        if "error" in result:
            logger.warning("nexus_alert_failed", action=action, error=result.get("detail", ""))
        else:
            logger.info("nexus_alert_sent", action=action, job_id=result.get("job_id", ""))
    except Exception as exc:
        logger.warning("nexus_alert_exception", action=action, error=str(exc)[:200])
