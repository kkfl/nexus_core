"""Unit tests for the redaction module."""

from apps.secrets_agent.crypto.redaction import SafeValue, redact, sanitize_dict


def test_safe_value_str_is_redacted():
    sv = SafeValue("my-secret-password")
    assert str(sv) == "[REDACTED]"
    assert repr(sv) == "[REDACTED]"
    assert f"{sv}" == "[REDACTED]"


def test_safe_value_unsafe_access():
    sv = SafeValue("my-secret-password")
    assert sv.unsafe_value == "my-secret-password"


def test_redact_returns_redacted():
    assert redact("any-value") == "[REDACTED]"


def test_sanitize_dict_redacts_secret_keys():
    data = {
        "username": "admin",
        "password": "super-secret",
        "api_key": "key-12345",
        "token": "eyJ...",
        "normal_field": "safe-value",
    }
    sanitized = sanitize_dict(data)
    assert sanitized["username"] == "admin"
    assert sanitized["normal_field"] == "safe-value"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"


def test_sanitize_dict_nested():
    data = {
        "outer": "safe",
        "credentials": {
            "password": "secret",
            "user": "alice",
        },
    }
    sanitized = sanitize_dict(data)
    assert sanitized["outer"] == "safe"
    assert sanitized["credentials"]["password"] == "[REDACTED]"
    assert sanitized["credentials"]["user"] == "alice"


def test_secret_value_not_logged_via_safe_value(capsys):
    """Simulates accidentally passing a SafeValue to print/format."""
    sv = SafeValue("do-not-log-me")
    print(f"Retrieved secret: {sv}")
    captured = capsys.readouterr()
    assert "do-not-log-me" not in captured.out
    assert "[REDACTED]" in captured.out
