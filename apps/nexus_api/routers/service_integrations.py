"""
Service Integrations API — manage external service registrations, API keys,
permissions, and usage tracking.

All endpoints require admin role and are mounted at /portal/service-integrations.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.nexus_api.dependencies import RequireRole
from packages.shared.db import get_db
from packages.shared.models.core import ServiceIntegration, ServiceUsageLog, User

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    service_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    description: str | None = None
    permissions: list[str] = Field(default=["secrets:read", "secrets:list"])
    alias_pattern: str = Field(default="*", max_length=255)
    rate_limit_rpm: int | None = Field(default=None, ge=1)
    daily_request_limit: int | None = Field(default=None, ge=1)


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None
    alias_pattern: str | None = None
    rate_limit_rpm: int | None = None
    daily_request_limit: int | None = None
    is_active: bool | None = None


class ServiceResponse(BaseModel):
    id: str
    name: str
    service_id: str
    api_key_prefix: str
    description: str | None
    permissions: list[str]
    alias_pattern: str
    rate_limit_rpm: int | None
    daily_request_limit: int | None
    is_active: bool
    last_seen_at: str | None
    created_at: str
    requests_24h: int = 0
    requests_30d: int = 0


class ServiceCreateResponse(ServiceResponse):
    """Returned only on creation — includes the plaintext API key (shown once)."""

    api_key: str


class UsageStats(BaseModel):
    service_id: str
    requests_today: int
    requests_7d: int
    requests_30d: int
    recent_requests: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_api_key() -> tuple[str, str, str]:
    """Generate an API key. Returns (plaintext, sha256_hash, prefix)."""
    raw = secrets.token_hex(24)  # 48 hex chars
    plaintext = f"nxs_{raw}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    prefix = plaintext[:12]  # "nxs_" + 8 chars
    return plaintext, key_hash, prefix


def _fmt_dt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def _get_usage_counts(db: AsyncSession, service_id: str) -> tuple[int, int]:
    """Return (requests_24h, requests_30d) for a service."""
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    month_ago = now - timedelta(days=30)

    r24 = await db.execute(
        select(func.count(ServiceUsageLog.id)).where(
            ServiceUsageLog.service_id == service_id,
            ServiceUsageLog.ts >= day_ago,
        )
    )
    r30 = await db.execute(
        select(func.count(ServiceUsageLog.id)).where(
            ServiceUsageLog.service_id == service_id,
            ServiceUsageLog.ts >= month_ago,
        )
    )
    return r24.scalar() or 0, r30.scalar() or 0


async def _to_response(db: AsyncSession, svc: ServiceIntegration) -> ServiceResponse:
    r24, r30 = await _get_usage_counts(db, svc.service_id)
    return ServiceResponse(
        id=svc.id,
        name=svc.name,
        service_id=svc.service_id,
        api_key_prefix=svc.api_key_prefix,
        description=svc.description,
        permissions=svc.permissions or [],
        alias_pattern=svc.alias_pattern,
        rate_limit_rpm=svc.rate_limit_rpm,
        daily_request_limit=svc.daily_request_limit,
        is_active=svc.is_active,
        last_seen_at=_fmt_dt(svc.last_seen_at),
        created_at=_fmt_dt(svc.created_at),
        requests_24h=r24,
        requests_30d=r30,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
async def list_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> list[dict[str, Any]]:
    """List all registered service integrations with usage stats."""
    result = await db.execute(select(ServiceIntegration).order_by(ServiceIntegration.name))
    services = result.scalars().all()
    return [(await _to_response(db, svc)).model_dump() for svc in services]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Register a new service integration. Returns the API key ONCE."""
    # Check for duplicate service_id
    existing = await db.execute(
        select(ServiceIntegration).where(ServiceIntegration.service_id == payload.service_id)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service '{payload.service_id}' already exists.",
        )

    plaintext_key, key_hash, prefix = _generate_api_key()

    svc = ServiceIntegration(
        id=str(uuid.uuid4()),
        name=payload.name,
        service_id=payload.service_id,
        api_key_hash=key_hash,
        api_key_prefix=prefix,
        description=payload.description,
        permissions=payload.permissions,
        alias_pattern=payload.alias_pattern,
        rate_limit_rpm=payload.rate_limit_rpm,
        daily_request_limit=payload.daily_request_limit,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)

    resp = await _to_response(db, svc)
    return ServiceCreateResponse(
        **resp.model_dump(),
        api_key=plaintext_key,
    ).model_dump()


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> dict[str, Any]:
    """Get service details by ID or service_id."""
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")
    return (await _to_response(db, svc)).model_dump()


@router.patch("/{service_id}")
async def update_service(
    service_id: str,
    payload: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Update service name, limits, permissions, etc."""
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(svc, key, value)
        svc.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(svc)

    return (await _to_response(db, svc)).model_dump()


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> None:
    """Revoke and delete a service integration."""
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")

    # Delete usage log entries
    await db.execute(delete(ServiceUsageLog).where(ServiceUsageLog.service_id == svc.service_id))
    await db.delete(svc)
    await db.commit()


@router.post("/{service_id}/regenerate-key")
async def regenerate_key(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Generate a new API key for a service (invalidates the old one)."""
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")

    plaintext_key, key_hash, prefix = _generate_api_key()
    svc.api_key_hash = key_hash
    svc.api_key_prefix = prefix
    svc.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(svc)

    resp = await _to_response(db, svc)
    return ServiceCreateResponse(
        **resp.model_dump(),
        api_key=plaintext_key,
    ).model_dump()


@router.get("/{service_id}/usage")
async def get_usage(
    service_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin", "operator"])),
) -> dict[str, Any]:
    """Get usage stats and recent request log for a service."""
    # Resolve to canonical service_id
    svc_result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = svc_result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")

    sid = svc.service_id
    now = datetime.now(UTC)

    # Count requests in different time windows
    counts = {}
    for label, delta in [
        ("today", timedelta(days=1)),
        ("7d", timedelta(days=7)),
        ("30d", timedelta(days=30)),
    ]:
        r = await db.execute(
            select(func.count(ServiceUsageLog.id)).where(
                ServiceUsageLog.service_id == sid,
                ServiceUsageLog.ts >= now - delta,
            )
        )
        counts[f"requests_{label}"] = r.scalar() or 0

    # Recent requests
    recent = await db.execute(
        select(ServiceUsageLog)
        .where(ServiceUsageLog.service_id == sid)
        .order_by(ServiceUsageLog.ts.desc())
        .limit(limit)
    )
    recent_list = [
        {
            "id": row.id,
            "endpoint": row.endpoint,
            "method": row.method,
            "status_code": row.status_code,
            "ip_address": row.ip_address,
            "ts": _fmt_dt(row.ts),
        }
        for row in recent.scalars().all()
    ]

    return UsageStats(
        service_id=sid,
        requests_today=counts["requests_today"],
        requests_7d=counts["requests_7d"],
        requests_30d=counts["requests_30d"],
        recent_requests=recent_list,
    ).model_dump()
