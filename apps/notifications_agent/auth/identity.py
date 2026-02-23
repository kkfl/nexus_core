"""
notifications_agent auth: X-Service-ID + X-Agent-Key header validation.
Same pattern as all other Nexus agents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from fastapi import Header, HTTPException, Request, status

from apps.notifications_agent.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class ServiceIdentity:
    service_id: str
    is_admin: bool
    ip_address: str | None
    request_id: str
    correlation_id: str


def get_service_identity(
    request: Request,
    x_service_id: str = Header(..., alias="X-Service-ID"),
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
) -> ServiceIdentity:
    settings = get_settings()
    agent_keys = settings.get_agent_keys()

    expected = agent_keys.get(x_service_id)
    if not expected or expected != x_agent_key:
        logger.warning(
            "notifications_auth_failed",
            service_id=x_service_id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials.",
        )

    correlation_id = x_correlation_id or x_request_id or str(uuid.uuid4())
    import structlog as sl

    sl.contextvars.bind_contextvars(service_id=x_service_id, correlation_id=correlation_id)

    return ServiceIdentity(
        service_id=x_service_id,
        is_admin=(x_service_id == "admin"),
        ip_address=request.client.host if request.client else None,
        request_id=x_request_id or correlation_id,
        correlation_id=correlation_id,
    )


def require_admin(identity: ServiceIdentity) -> ServiceIdentity:
    """Raise 403 if caller is not admin."""
    if not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return identity
