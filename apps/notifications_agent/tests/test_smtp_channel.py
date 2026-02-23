"""
Unit tests for SMTP email channel.
Covers: send success, no destination guard, credential redaction, MIME multipart structure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.notifications_agent.channels.smtp import SmtpChannel


@pytest.fixture
def channel():
    return SmtpChannel(
        host="smtp.example.com",
        port=587,
        username="sender@example.com",
        password="super_secret_password_xyz",
        from_address="Nexus Alerts <noreply@example.com>",
        use_tls=False,
    )


def test_repr_redacts_password(channel):
    r = repr(channel)
    assert "super_secret_password_xyz" not in r
    assert "[REDACTED]" in r


@pytest.mark.asyncio
async def test_send_no_destination_returns_failure(channel):
    result = await channel.send(subject="Alert", body="Something happened", destination=None)
    assert result.success is False
    assert result.error_code == "no_destination"


@pytest.mark.asyncio
async def test_send_success(channel):
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (None, "250 OK")
        result = await channel.send(
            subject="Test Alert",
            body="An agent went down.",
            destination="ops@example.com",
            context={"correlation_id": "test-corr-123"},
        )
    assert result.success is True
    assert result.provider_msg_id is not None
    assert result.destination_hash  # sha256 of ops@example.com


@pytest.mark.asyncio
async def test_send_success_mime_structure(channel):
    """Verify aiosmtplib.send is called with a MIMEMultipart message."""
    captured = {}

    async def fake_send(msg, **kwargs):
        captured["msg"] = msg

    with patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=fake_send):
        await channel.send(subject="Test", body="Body text", destination="ops@example.com")

    msg = captured.get("msg")
    assert msg is not None
    assert msg["Subject"] == "Test"
    assert msg["To"] == "ops@example.com"
    assert "Message-ID" in msg
    # Should contain both plain and HTML parts
    payloads = msg.get_payload()
    content_types = [p.get_content_type() for p in payloads]
    assert "text/plain" in content_types
    assert "text/html" in content_types


@pytest.mark.asyncio
async def test_send_failure_redacts_password(channel):
    """SMTP exception message must not log the password."""
    import aiosmtplib

    async def raise_smtp(*args, **kwargs):
        raise aiosmtplib.SMTPAuthenticationError(
            535, "Authentication failed: super_secret_password_xyz"
        )

    with patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=raise_smtp):
        result = await channel.send(subject="X", body="Y", destination="ops@example.com")

    assert result.success is False
    assert result.error_code == "smtp_error"
    # Password must be redacted from stored error detail
    assert "super_secret_password_xyz" not in (result.error_detail or "")


@pytest.mark.asyncio
async def test_destination_hash_is_sha256(channel):
    """destination_hash must be sha256 of the email address."""
    import hashlib

    with patch("aiosmtplib.send", new_callable=AsyncMock):
        result = await channel.send(subject="X", body="Y", destination="test@example.com")
    expected_hash = hashlib.sha256(b"test@example.com").hexdigest()
    assert result.destination_hash == expected_hash
