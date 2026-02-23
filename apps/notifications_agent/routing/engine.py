"""
Routing engine — resolves which channels to use for a given tenant/env/severity.
Prefers explicit channels on request; falls back to routing rules; final fallback: telegram.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.notifications_agent.store.postgres import resolve_routing_rule

logger = structlog.get_logger(__name__)

# Default fallback routing: critical/error → telegram; warn/info → telegram only
_DEFAULT_ROUTES: dict[str, list[str]] = {
    "critical": ["telegram", "email"],
    "error": ["telegram"],
    "warn": ["telegram"],
    "info": ["telegram"],
}


async def resolve_channels(
    db: AsyncSession,
    *,
    tenant_id: str,
    env: str,
    severity: str,
    requested_channels: list[str] | None = None,
    routing_rule_id: str | None = None,
) -> tuple[list[str], dict | None]:
    """
    Determine which channels to use and return channel config from routing rule (if any).
    Returns (channels, rule_config).
    """
    if requested_channels:
        return requested_channels, None

    rule = await resolve_routing_rule(db, tenant_id, env, severity)
    if rule:
        logger.info(
            "routing_rule_matched", rule_id=str(rule.id), severity=severity, channels=rule.channels
        )
        return rule.channels, rule.config or {}

    # Default fallback
    channels = _DEFAULT_ROUTES.get(severity, ["telegram"])
    logger.info("routing_default_fallback", severity=severity, channels=channels)
    return channels, None
