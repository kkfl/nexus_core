"""
IP Allowlist — Settings → Security

CRUD for IP allowlist entries + enforcement middleware.
When entries exist, only matching CIDRs can access the API (fail-open if empty).
"""

import ipaddress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireModuleAccess
from apps.nexus_api.security_alerts import send_security_alert
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models import IpAllowlistEntry, User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────
class IpAllowlistCreate(BaseModel):
    cidr: str
    label: str

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {v}")
        return str(ipaddress.ip_network(v, strict=False))


class IpAllowlistOut(BaseModel):
    id: int
    cidr: str
    label: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────
@router.get("/", response_model=list[IpAllowlistOut])
async def list_ip_allowlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("ip_allowlist", "manage")),
) -> Any:
    res = await db.execute(select(IpAllowlistEntry).order_by(IpAllowlistEntry.created_at.desc()))
    return res.scalars().all()


@router.post("/", response_model=IpAllowlistOut, status_code=201)
async def create_ip_allowlist_entry(
    body: IpAllowlistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("ip_allowlist", "manage")),
) -> Any:
    entry = IpAllowlistEntry(cidr=body.cidr, label=body.label)
    db.add(entry)
    log_audit_event(
        db,
        "ip_allowlist_add",
        "ip_allowlist",
        current_user,
        None,
        {"cidr": body.cidr, "label": body.label},
    )
    await db.commit()
    await db.refresh(entry)
    send_security_alert(
        "ip_allowlist_add",
        current_user.email,
        f"CIDR: {body.cidr} — {body.label}",
    )
    return entry


@router.patch("/{entry_id}")
async def toggle_ip_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("ip_allowlist", "manage")),
) -> Any:
    res = await db.execute(select(IpAllowlistEntry).where(IpAllowlistEntry.id == entry_id))
    entry = res.scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry.is_active = not entry.is_active
    log_audit_event(
        db,
        "ip_allowlist_toggle",
        "ip_allowlist",
        current_user,
        str(entry_id),
        {"cidr": entry.cidr, "is_active": entry.is_active},
    )
    await db.commit()
    send_security_alert(
        "ip_allowlist_toggle",
        current_user.email,
        f"CIDR: {entry.cidr} — {'enabled' if entry.is_active else 'disabled'}",
    )
    return {"id": entry.id, "is_active": entry.is_active}


@router.delete("/{entry_id}")
async def delete_ip_allowlist_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireModuleAccess("ip_allowlist", "manage")),
) -> Any:
    res = await db.execute(select(IpAllowlistEntry).where(IpAllowlistEntry.id == entry_id))
    entry = res.scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    cidr = entry.cidr
    await db.delete(entry)
    log_audit_event(
        db,
        "ip_allowlist_remove",
        "ip_allowlist",
        current_user,
        str(entry_id),
        {"cidr": cidr},
    )
    await db.commit()
    send_security_alert(
        "ip_allowlist_remove",
        current_user.email,
        f"CIDR removed: {cidr}",
    )
    return {"status": "deleted"}
