import json
import re
from typing import Any

# Basic sensitive patterns
CRED_PATTERN = re.compile(
    r'(?i)(password|secret|token|key|pwd|auth|credential)[\s\=\:]+[\'"]?([^\s\'"]+)[\'"]?'
)


def redact_string(s: str) -> str:
    """Simple redaction for potential secrets in strings."""
    # This is a naive implementation; production would use more robust regexes or presidio.
    return CRED_PATTERN.sub(r"\1=***REDACTED***", s)


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact dictionary values."""
    if not isinstance(data, dict):
        return data

    redacted = {}
    for k, v in data.items():
        k_lower = k.lower()
        if any(term in k_lower for term in ["password", "secret", "token", "key", "auth"]):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        elif isinstance(v, list):
            redacted[k] = [
                redact_dict(i)
                if isinstance(i, dict)
                else (redact_string(str(i)) if isinstance(i, str) else i)
                for i in v
            ]
        elif isinstance(v, str):
            redacted[k] = redact_string(v)
        else:
            redacted[k] = v
    return redacted


def ensure_safe_output(output: Any) -> dict[str, Any]:
    """Wraps output in a dict and ensures it is redacted before saving to DB."""
    if not isinstance(output, dict):
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"raw_output": output}
        else:
            output = {"output": str(output)}

    return redact_dict(output)
