from packages.shared.logging import redact_dict


def test_log_redaction():
    # Setup
    payload = {
        "user": "admin",
        "password": "supersecretpassword",
        "api_key": "sk-1234567890",
        "nested": {"token": "bearer xyz", "Authorization": "Basic 123", "safe_value": 42},
        "set-cookie": "session=invalid",
    }

    # Execute
    redacted = redact_dict(payload)

    # Assert
    assert redacted["user"] == "admin"
    assert redacted["password"] == "***REDACTED***"
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["nested"]["Authorization"] == "***REDACTED***"
    assert redacted["nested"]["safe_value"] == 42
    assert redacted["set-cookie"] == "***REDACTED***"


def test_log_redaction_lists():
    payload = {"items": [{"secret": "hide_me"}, {"public": "show_me"}]}

    redacted = redact_dict(payload)

    assert redacted["items"][0]["secret"] == "***REDACTED***"
    assert redacted["items"][1]["public"] == "show_me"
