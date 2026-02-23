"""
Unit tests for the routing engine.
Covers: explicit channel passthrough, DB rule match, wildcard fallback, default routes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.notifications_agent.routing.engine import resolve_channels


def _make_rule(channels, config=None):
    rule = MagicMock()
    rule.id = "rule-uuid-1234"
    rule.channels = channels
    rule.config = config or {}
    return rule


@pytest.mark.asyncio
async def test_explicit_channels_bypass_routing():
    """If explicit channels are provided, routing DB is never consulted."""
    mock_db = AsyncMock()
    channels, rule_config = await resolve_channels(
        mock_db,
        tenant_id="nexus",
        env="prod",
        severity="critical",
        requested_channels=["telegram", "email"],
    )
    assert channels == ["telegram", "email"]
    assert rule_config is None
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_db_rule_exact_match():
    """Exact severity match in DB → returns rule channels + config."""
    mock_db = AsyncMock()
    rule = _make_rule(["telegram", "webhook"], config={"webhook_url": "https://hooks.example.com"})

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=rule),
    ):
        channels, rule_config = await resolve_channels(
            mock_db,
            tenant_id="nexus",
            env="prod",
            severity="error",
        )

    assert channels == ["telegram", "webhook"]
    assert rule_config == {"webhook_url": "https://hooks.example.com"}


@pytest.mark.asyncio
async def test_db_rule_not_found_uses_default():
    """No DB rule → falls back to _DEFAULT_ROUTES."""
    mock_db = AsyncMock()

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=None),
    ):
        channels, rule_config = await resolve_channels(
            mock_db,
            tenant_id="nexus",
            env="prod",
            severity="critical",
        )

    assert channels == ["telegram", "email"]
    assert rule_config is None


@pytest.mark.asyncio
async def test_default_fallback_error_severity():
    mock_db = AsyncMock()
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=None),
    ):
        channels, _ = await resolve_channels(
            mock_db, tenant_id="nexus", env="prod", severity="error"
        )
    assert channels == ["telegram"]


@pytest.mark.asyncio
async def test_default_fallback_warn_severity():
    mock_db = AsyncMock()
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=None),
    ):
        channels, _ = await resolve_channels(
            mock_db, tenant_id="nexus", env="prod", severity="warn"
        )
    assert channels == ["telegram"]


@pytest.mark.asyncio
async def test_default_fallback_info_severity():
    mock_db = AsyncMock()
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=None),
    ):
        channels, _ = await resolve_channels(
            mock_db, tenant_id="nexus", env="prod", severity="info"
        )
    assert "telegram" in channels


@pytest.mark.asyncio
async def test_unknown_severity_still_returns_telegram():
    """Unknown severity should not crash; defaults to telegram via .get fallback."""
    mock_db = AsyncMock()
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "apps.notifications_agent.routing.engine.resolve_routing_rule",
        new=AsyncMock(return_value=None),
    ):
        channels, _ = await resolve_channels(
            mock_db, tenant_id="nexus", env="prod", severity="unknown_sev"
        )
    assert channels == ["telegram"]
