"""Unit tests for Webhook channel — HMAC signing, retry, URL hash."""
from __future__ import annotations

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, patch

import httpx

from apps.notifications_agent.channels.webhook import WebhookChannel, _sign_payload


def _mock_resp(status: int = 200, body: bytes = b"ok") -> httpx.Response:
    return httpx.Response(status, content=body)


@pytest.fixture
def channel():
    return WebhookChannel(signing_secret="super_secret_signing_key_xyz")


def test_repr_redacts_secret(channel):
    assert "super_secret_signing_key_xyz" not in repr(channel)


def test_sign_payload():
    sig = _sign_payload("my_secret", b'{"test":1}')
    assert sig.startswith("sha256=")
    expected = "sha256=" + hmac.new(b"my_secret", b'{"test":1}', hashlib.sha256).hexdigest()
    assert sig == expected


@pytest.mark.asyncio
async def test_send_success(channel):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(200)
        result = await channel.send(
            subject="alert", body="test body",
            destination="https://example.com/webhook",
            context={"correlation_id": "abc-123"},
        )
    assert result.success is True
    # Verify signature header was sent
    call_kwargs = mock_post.call_args.kwargs
    assert "X-Nexus-Signature" in call_kwargs.get("headers", {})
    assert call_kwargs["headers"]["X-Nexus-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_send_no_url(channel):
    result = await channel.send(subject="x", body="y", destination=None)
    assert result.success is False
    assert result.error_code == "no_destination"


@pytest.mark.asyncio
async def test_send_http_error(channel):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(500, b"internal error")
        result = await channel.send(subject="x", body="y",
                                    destination="https://example.com/wh")
    assert result.success is False
    assert result.error_code == "http_500"


"""Unit tests for template engine."""
from apps.notifications_agent.templates.engine import render_template, BUILTIN_TEMPLATES


def test_builtin_agent_down():
    subject, body = render_template(
        "agent_down",
        {"agent": "dns-agent", "reason": "OOM", "env": "prod"},
    )
    assert "dns-agent" in body
    assert "OOM" in body
    assert subject is not None
    assert "dns-agent" in subject


def test_builtin_generic_raw():
    subject, body = render_template(
        "generic",
        {"subject": "Test", "body": "Hello world"},
    )
    assert body == "Hello world"
    assert subject == "Test"


def test_unknown_template_uses_override():
    subject, body = render_template(
        "nonexistent_tpl",
        None,
        subject_override="My Subject",
        body_override="My Body",
    )
    assert body == "My Body"
    assert subject == "My Subject"


def test_context_injection_timestamp():
    _, body = render_template("agent_down", {"agent": "x", "reason": "y", "env": "prod"})
    assert "UTC" in body  # timestamp injected
