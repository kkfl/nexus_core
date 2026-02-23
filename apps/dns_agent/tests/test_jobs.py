"""Job runner tests — state machine, retry logic, and safe error redaction."""
from __future__ import annotations

import pytest
import re

from apps.dns_agent.jobs.runner import _safe_error


def test_safe_error_redacts_token_shaped_strings():
    """Tokens (32+ char alphanumeric) must be redacted from error messages."""
    fake_token = "cf_token_abc123_very_long_key_123456789"
    msg = f"Invalid token: Bearer {fake_token} was rejected"
    result = _safe_error(Exception(msg))
    assert fake_token not in result
    assert "[REDACTED]" in result


def test_safe_error_preserves_regular_messages():
    """Short, non-token error messages should be preserved."""
    msg = "Zone 'example.com' not found."
    result = _safe_error(Exception(msg))
    assert "Zone" in result
    assert "example.com" in result


def test_safe_error_truncates_to_2000_chars():
    """Errors should be truncated to avoid huge log entries."""
    long_msg = "a" * 5000
    result = _safe_error(Exception(long_msg))
    assert len(result) <= 2000
