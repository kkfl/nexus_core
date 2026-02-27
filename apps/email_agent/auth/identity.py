"""
email_agent — service identity auth (X-Service-ID + X-Agent-Key).
"""

from __future__ import annotations

import contextlib
import json
import os

from fastapi import Header, HTTPException


async def verify_service_identity(
    x_service_id: str = Header(...),
    x_agent_key: str = Header(...),
) -> str:
    """Validate caller identity. Returns service_id."""
    allowed_keys: dict[str, str] = {}
    raw = os.environ.get("EMAIL_AGENT_KEYS", "")
    if raw:
        with contextlib.suppress(Exception):
            allowed_keys = json.loads(raw)

    # Fallback: accept the default dev key
    if not allowed_keys:
        allowed_keys = {
            "nexus": "nexus-email-key-change-me",
            "admin": "admin-email-key",
        }

    expected = allowed_keys.get(x_service_id)
    if not expected or expected != x_agent_key:
        raise HTTPException(status_code=401, detail="Invalid service credentials")
    return x_service_id
