"""
Unit tests for Telegram channel.
Covers: send, MarkdownV2 escaping, truncation, rate limit retry, token redaction.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from apps.notifications_agent.channels.telegram import (
    _TG_MAX_LEN,
    TelegramChannel,
    _truncate,
    escape_markdown_v2,
)


def _mock_resp(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
def channel():
    return TelegramChannel(token="SECRET_BOT_TOKEN_12345", default_chat_id="-100123456")


def test_repr_redacts_token(channel):
    r = repr(channel)
    assert "SECRET_BOT_TOKEN_12345" not in r
    assert "[REDACTED]" in r


def test_escape_markdown_basic():
    raw = "Hello world! Cost: $10.00 (approx)"
    escaped = escape_markdown_v2(raw)
    for ch in r"\.!()":
        assert f"\\{ch}" in escaped or ch not in raw


def test_escape_markdown_no_double_escape():
    text = "test.txt"
    escaped = escape_markdown_v2(text)
    assert "\\." in escaped
    # Should not be double-escaped
    assert "\\\\." not in escaped


def test_truncate_short():
    text = "Hello"
    assert _truncate(text) == "Hello"


def test_truncate_long():
    text = "A" * (_TG_MAX_LEN + 100)
    result = _truncate(text)
    assert len(result) <= _TG_MAX_LEN
    assert "truncated" in result


@pytest.mark.asyncio
async def test_send_success(channel):
    payload = {"ok": True, "result": {"message_id": 42}}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(payload)
        result = await channel.send(subject="Test Alert", body="Something happened")
    assert result.success is True
    assert result.provider_msg_id == "42"


@pytest.mark.asyncio
async def test_send_no_destination_returns_failure():
    ch = TelegramChannel(token="tok", default_chat_id="")
    result = await ch.send(subject="X", body="Y", destination=None)
    assert result.success is False
    assert result.error_code == "no_destination"


@pytest.mark.asyncio
async def test_send_api_error(channel):
    payload = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_resp(payload)
        result = await channel.send(subject="X", body="Y")
    assert result.success is False
    assert "SECRET_BOT_TOKEN_12345" not in (result.error_detail or "")


@pytest.mark.asyncio
async def test_rate_limit_retry(channel):
    """429 with Retry-After should retry and succeed."""
    rate_limit = httpx.Response(
        429,
        content=b'{"ok":false}',
        headers={"Retry-After": "0.01", "Content-Type": "application/json"},
    )
    success = _mock_resp({"ok": True, "result": {"message_id": 99}})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [rate_limit, success]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await channel.send(subject="X", body="Y")
    assert result.success is True
    assert mock_post.call_count == 2
