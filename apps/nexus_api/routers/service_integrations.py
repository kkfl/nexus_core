"""
Service Integrations API — manage external service registrations, API keys,
permissions, and usage tracking.

All endpoints require admin role and are mounted at /portal/service-integrations.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.nexus_api.dependencies import RequireModuleAccess, RequireRole, verify_password
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models.core import User
from packages.shared.secrets import decrypt_secret, encrypt_secret
from packages.shared.service_integration_models import (
    ServiceIntegration,
    ServicePermissionRule,
    ServiceUsageLog,
)

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


class RuleCreate(BaseModel):
    resource_type: str = Field(..., min_length=1, max_length=64)
    resource_pattern: str = Field(default="*", max_length=255)
    actions: list[str] = Field(default=["read"])
    rate_limit_rpm: int | None = Field(default=None, ge=1)
    daily_limit: int | None = Field(default=None, ge=1)


class RuleUpdate(BaseModel):
    resource_type: str | None = None
    resource_pattern: str | None = None
    actions: list[str] | None = None
    rate_limit_rpm: int | None = None
    daily_limit: int | None = None
    is_active: bool | None = None


class RuleResponse(BaseModel):
    id: str
    service_integration_id: str
    resource_type: str
    resource_pattern: str
    actions: list[str]
    rate_limit_rpm: int | None
    daily_limit: int | None
    is_active: bool
    created_at: str | None


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
    r24 = await db.execute(
        select(func.count(ServiceUsageLog.id)).where(
            ServiceUsageLog.service_id == service_id,
            ServiceUsageLog.ts >= func.now() - timedelta(days=1),
        )
    )
    r30 = await db.execute(
        select(func.count(ServiceUsageLog.id)).where(
            ServiceUsageLog.service_id == service_id,
            ServiceUsageLog.ts >= func.now() - timedelta(days=30),
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
    current_user: User = Depends(RequireModuleAccess("integrations", "manage")),
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
    encrypted_key = encrypt_secret(plaintext_key)

    svc = ServiceIntegration(
        id=str(uuid.uuid4()),
        name=payload.name,
        service_id=payload.service_id,
        api_key_hash=key_hash,
        api_key_prefix=prefix,
        api_key_enc=encrypted_key,
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
    current_user: User = Depends(RequireModuleAccess("integrations", "manage")),
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
    svc.api_key_enc = encrypt_secret(plaintext_key)
    await db.commit()
    await db.refresh(svc)

    resp = await _to_response(db, svc)
    return ServiceCreateResponse(
        **resp.model_dump(),
        api_key=plaintext_key,
    ).model_dump()


class RevealKeyRequest(BaseModel):
    """Payload for break-glass API key reveal."""

    password: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/{service_id}/reveal-key")
async def reveal_key(
    service_id: str,
    payload: RevealKeyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Break-glass: reveal the full API key (requires password + reason)."""
    # 1. Verify admin password
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    # 2. Find the service
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")

    # 3. Ensure encrypted key exists (legacy keys won't have it)
    if not svc.api_key_enc:
        raise HTTPException(
            status_code=404,
            detail="Encrypted key not available. Regenerate the key to enable reveal.",
        )

    # 4. Decrypt
    plaintext_key = decrypt_secret(svc.api_key_enc)

    # 5. Audit trail
    log_audit_event(
        db,
        "service_key_revealed",
        "service_integration",
        current_user,
        None,
        {"reason": payload.reason, "service_id": svc.service_id, "service_name": svc.name},
    )
    await db.commit()

    return {"api_key": plaintext_key, "service_id": svc.service_id}


@router.get("/{service_id}/usage")
async def get_usage(
    service_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("integrations", "manage")),
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
                ServiceUsageLog.ts >= func.now() - delta,
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


# ---------------------------------------------------------------------------
# Permission Rule Routes
# ---------------------------------------------------------------------------


async def _resolve_service(db: AsyncSession, service_id: str) -> ServiceIntegration:
    """Find a service by id or service_id, or 404."""
    result = await db.execute(
        select(ServiceIntegration).where(
            (ServiceIntegration.id == service_id) | (ServiceIntegration.service_id == service_id)
        )
    )
    svc = result.scalars().first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found.")
    return svc


@router.get("/{service_id}/rules")
async def list_rules(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("integrations", "manage")),
) -> list[dict[str, Any]]:
    """List all permission rules for a service."""
    svc = await _resolve_service(db, service_id)
    result = await db.execute(
        select(ServicePermissionRule)
        .where(ServicePermissionRule.service_integration_id == svc.id)
        .order_by(ServicePermissionRule.resource_type, ServicePermissionRule.resource_pattern)
    )
    rules = result.scalars().all()
    return [
        RuleResponse(
            id=r.id,
            service_integration_id=r.service_integration_id,
            resource_type=r.resource_type,
            resource_pattern=r.resource_pattern,
            actions=r.actions or [],
            rate_limit_rpm=r.rate_limit_rpm,
            daily_limit=r.daily_limit,
            is_active=r.is_active,
            created_at=_fmt_dt(r.created_at),
        ).model_dump()
        for r in rules
    ]


@router.post("/{service_id}/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    service_id: str,
    payload: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Add a permission rule to a service."""
    svc = await _resolve_service(db, service_id)
    rule = ServicePermissionRule(
        id=str(uuid.uuid4()),
        service_integration_id=svc.id,
        resource_type=payload.resource_type,
        resource_pattern=payload.resource_pattern,
        actions=payload.actions,
        rate_limit_rpm=payload.rate_limit_rpm,
        daily_limit=payload.daily_limit,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return RuleResponse(
        id=rule.id,
        service_integration_id=rule.service_integration_id,
        resource_type=rule.resource_type,
        resource_pattern=rule.resource_pattern,
        actions=rule.actions or [],
        rate_limit_rpm=rule.rate_limit_rpm,
        daily_limit=rule.daily_limit,
        is_active=rule.is_active,
        created_at=_fmt_dt(rule.created_at),
    ).model_dump()


@router.patch("/{service_id}/rules/{rule_id}")
async def update_rule(
    service_id: str,
    rule_id: str,
    payload: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> dict[str, Any]:
    """Update a permission rule."""
    svc = await _resolve_service(db, service_id)
    result = await db.execute(
        select(ServicePermissionRule).where(
            ServicePermissionRule.id == rule_id,
            ServicePermissionRule.service_integration_id == svc.id,
        )
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    await db.commit()
    await db.refresh(rule)
    return RuleResponse(
        id=rule.id,
        service_integration_id=rule.service_integration_id,
        resource_type=rule.resource_type,
        resource_pattern=rule.resource_pattern,
        actions=rule.actions or [],
        rate_limit_rpm=rule.rate_limit_rpm,
        daily_limit=rule.daily_limit,
        is_active=rule.is_active,
        created_at=_fmt_dt(rule.created_at),
    ).model_dump()


@router.delete("/{service_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    service_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(["admin"])),
) -> None:
    """Delete a permission rule."""
    svc = await _resolve_service(db, service_id)
    result = await db.execute(
        select(ServicePermissionRule).where(
            ServicePermissionRule.id == rule_id,
            ServicePermissionRule.service_integration_id == svc.id,
        )
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    await db.delete(rule)
    await db.commit()
