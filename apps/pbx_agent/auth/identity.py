"""
pbx_agent inbound authentication.
Validates X-Service-ID + X-Agent-Key headers against PBX_AGENT_KEYS env var.
"""
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, HTTPException, Request
from apps.pbx_agent.config import config


@dataclass
class ServiceIdentity:
    service_id: str
    is_admin: bool
    correlation_id: str
    # Read-only services can only call diagnostics + status
    read_only: bool = False


def _load_keys() -> dict:
    try:
        return json.loads(config.pbx_agent_keys)
    except Exception:
        return {}


READ_ONLY_SERVICES = {"monitoring-agent"}


def get_service_identity(request: Request) -> ServiceIdentity:
    keys = _load_keys()
    service_id = request.headers.get("X-Service-ID", "")
    agent_key = request.headers.get("X-Agent-Key", "")
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    if not service_id or not agent_key:
        raise HTTPException(status_code=401, detail="Missing X-Service-ID or X-Agent-Key")

    expected = keys.get(service_id)
    if not expected or expected != agent_key:
        raise HTTPException(status_code=403, detail=f"Invalid credentials for service '{service_id}'")

    return ServiceIdentity(
        service_id=service_id,
        is_admin=(service_id == "admin"),
        correlation_id=correlation_id,
        read_only=(service_id in READ_ONLY_SERVICES),
    )
