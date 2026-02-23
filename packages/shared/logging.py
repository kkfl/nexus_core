import logging
import re
from typing import Any

import structlog

REDACT_KEYS = re.compile(r"(?i)(password|secret|token|api_key|authorization|cookie|set-cookie)")


def redact_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if REDACT_KEYS.search(str(k)) else redact_dict(v))
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [redact_dict(item) for item in obj]
    return obj


def redaction_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor to redact sensitive keys."""
    event_dict = redact_dict(event_dict)

    # Special handling for Authorization headers if logged raw
    if (
        "headers" in event_dict
        and isinstance(event_dict["headers"], dict)
        and "authorization" in event_dict["headers"]
    ):
        event_dict["headers"]["authorization"] = "***REDACTED***"

    return event_dict


def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.contextvars.merge_contextvars,
            redaction_processor,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=logging.INFO)
