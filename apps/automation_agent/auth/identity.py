"""
ServiceIdentity — validates X-Service-ID + X-Agent-Key headers on every request.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import structlog
from fastapi import Header, HTTPException, Request, status

from apps.automation_agent.config import config

logger = structlog.get_logger(__name__)


@dataclass
class ServiceIdentity:
    service_id: str
    is_admin: bool
    ip_address: Optional[str]
    request_id: str
    correlation_id: str


def get_service_identity(
    request: Request,
    x_service_id: str = Header(..., alias="X-Service-ID"),
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
) -> ServiceIdentity:
    """FastAPI dependency — validates service identity from headers."""

    expected_key = config.automation_agent_keys.get(x_service_id)
    if not expected_key or expected_key != x_agent_key:
        logger.warning(
            "automation_auth_failed",
            service_id=x_service_id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials.",
        )

    correlation_id = x_correlation_id or x_request_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(
        service_id=x_service_id,
        correlation_id=correlation_id,
    )

    return ServiceIdentity(
        service_id=x_service_id,
        is_admin=(x_service_id == "admin"),
        ip_address=request.client.host if request.client else None,
        request_id=x_request_id or correlation_id,
        correlation_id=correlation_id,
    )
