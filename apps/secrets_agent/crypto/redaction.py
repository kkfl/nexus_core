"""
Automatic secret-value redaction for logs and error messages.

Rules:
- Secret plaintext values MUST NEVER appear in logs, exceptions, or API
  responses (other than the dedicated /read endpoint).
- Use redact() wherever a value might inadvertently be included.
- The SafeValue wrapper makes it impossible to accidentally log the real value.
"""
from __future__ import annotations

import re
from typing import Any

_REDACTED = "[REDACTED]"

# Patterns that suggest a value is a secret (for structured log sanitization)
_SECRET_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"private_key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]


class SafeValue:
    """
    A wrapper that prevents accidental logging of secret values.
    str() and repr() both return [REDACTED].
    Access .unsafe_value ONLY when you intentionally need the plaintext.
    """
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        object.__setattr__(self, "_value", value)

    def __repr__(self) -> str:
        return _REDACTED

    def __str__(self) -> str:
        return _REDACTED

    def __format__(self, format_spec: str) -> str:
        return _REDACTED

    @property
    def unsafe_value(self) -> str:
        """Intentional access only. Do not log or pass to string formatting."""
        return object.__getattribute__(self, "_value")


def redact(value: str) -> str:
    """Replace a value with [REDACTED]. Use for log messages."""
    return _REDACTED


def sanitize_dict(data: dict[str, Any], *, depth: int = 0) -> dict[str, Any]:
    """
    Recursively walk a dict and replace values whose KEYS suggest they are
    secrets. Safe for structured logging.
    """
    if depth > 5:
        return data
    result: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(k, str) and any(p.search(k) for p in _SECRET_KEY_PATTERNS):
            result[k] = _REDACTED
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, depth=depth + 1)
        else:
            result[k] = v
    return result
