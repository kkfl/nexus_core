"""
Redaction layer for pbx_agent.
Strips AMI secrets, passwords, tokens, and long base64 blobs from any string output.
"""

import re

_PATTERNS = [
    # AMI login/secret lines
    (
        re.compile(r"(?i)(secret|Secret|password|Password|md5|auth|token|key)\s*[:=]\s*\S+"),
        r"\1: [REDACTED]",
    ),
    # SIP auth headers
    (re.compile(r"(?i)(Authorization:\s*)\S+"), r"\1[REDACTED]"),
    # Long base64/hex blobs (private keys, tokens)
    (re.compile(r"[A-Za-z0-9+/=]{48,}"), "[REDACTED_BLOB]"),
    # PEM blocks
    (re.compile(r"-----BEGIN[^\n]+-----.*?-----END[^\n]+-----", re.DOTALL), "[REDACTED_PEM]"),
]

MAX_OUTPUT_BYTES = 200 * 1024  # 200 KB


def redact(text: str) -> str:
    """Apply all redaction patterns and cap size."""
    if not text:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > MAX_OUTPUT_BYTES:
        text = text[:MAX_OUTPUT_BYTES] + "\n...[TRUNCATED]"
    return text


def redact_dict(d: dict) -> dict:
    """Redact string values in a dict (shallow)."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = redact(v)
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        else:
            result[k] = v
    return result
