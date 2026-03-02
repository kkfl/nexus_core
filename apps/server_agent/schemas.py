"""
Pydantic schemas for the Server Agent API.

INVARIANT: No provider credentials appear in any schema.
           No plaintext API tokens, API keys, or secrets.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_VALID_PROVIDERS = {"vultr", "proxmox"}
_VALID_ENVS = {"dev", "stage", "prod"}
_VALID_POWER_ACTIONS = {"start", "stop", "reboot"}
_VALID_BACKUP_SCHEDULES = {"daily", "weekly", "monthly"}


# ---------------------------------------------------------------------------
# Host schemas
# ---------------------------------------------------------------------------


class HostCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    provider: str = Field(..., description="vultr | proxmox")
    label: str = Field(..., min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict, description="Provider-specific config")
    secret_alias: str = Field(..., min_length=1, max_length=255, description="Vault alias for credentials")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {_VALID_PROVIDERS}")
        return v


class HostOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    provider: str
    label: str
    config: dict[str, Any]
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Server schemas
# ---------------------------------------------------------------------------


class CreateServerRequest(BaseModel):
    host_id: str = Field(..., description="Provider connection to use")
    label: str = Field(..., min_length=1, max_length=255)
    hostname: str = Field(..., min_length=1, max_length=255)
    region: str = Field(..., min_length=1, description="Vultr region slug or Proxmox node")
    plan: str = Field(..., min_length=1, description="Vultr plan or Proxmox template")
    os_id: str = Field(..., min_length=1, description="OS image ID")
    ssh_keys: list[str] = Field(default_factory=list, max_length=10)
    tags: Any = Field(default_factory=dict)


class ServerOut(BaseModel):
    id: str
    host_id: str
    provider: str
    provider_instance_id: str
    label: str
    hostname: str | None = None
    os: str | None = None
    plan: str | None = None
    region: str | None = None
    ip_v4: str | None = None
    ip_v6: str | None = None
    status: str
    power_status: str | None = None
    vcpu_count: int | None = None
    ram_mb: int | None = None
    disk_gb: int | None = None
    tags: Any = None
    last_synced_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Console schemas
# ---------------------------------------------------------------------------


class ConsoleOut(BaseModel):
    url: str
    type: str  # vnc|novnc|webterm
    token: str | None = None
    expires_at: datetime.datetime | None = None


# ---------------------------------------------------------------------------
# Snapshot schemas
# ---------------------------------------------------------------------------


class SnapshotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)


class SnapshotOut(BaseModel):
    id: str
    instance_id: str
    provider_snapshot_id: str | None = None
    name: str
    description: str
    size_gb: float | None = None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Backup schemas
# ---------------------------------------------------------------------------


class BackupOut(BaseModel):
    id: str
    instance_id: str
    provider_backup_id: str | None = None
    backup_type: str
    size_gb: float | None = None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class BackupScheduleRequest(BaseModel):
    schedule_type: str = Field(..., description="daily|weekly|monthly")
    hour: int = Field(0, ge=0, le=23)
    dow: int | None = Field(None, ge=1, le=7, description="Day of week for weekly")
    dom: int | None = Field(None, ge=1, le=28, description="Day of month for monthly")

    @field_validator("schedule_type")
    @classmethod
    def validate_schedule_type(cls, v: str) -> str:
        if v not in _VALID_BACKUP_SCHEDULES:
            raise ValueError(f"schedule_type must be one of {_VALID_BACKUP_SCHEDULES}")
        return v


class BackupScheduleOut(BaseModel):
    schedule_type: str
    hour: int
    dow: int | None = None
    dom: int | None = None


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------


class JobOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    operation: str
    status: str
    instance_id: str | None = None
    attempts: int
    last_error: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_by_service_id: str
    correlation_id: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class JobCreateResponse(BaseModel):
    job_id: str
    status: str = "pending"
    message: str = "Change job queued."


# ---------------------------------------------------------------------------
# Audit schemas
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    id: str
    correlation_id: str
    service_id: str
    tenant_id: str
    env: str
    action: str
    instance_label: str | None = None
    provider: str | None = None
    result: str
    reason: str | None = None
    ip_address: str | None = None
    ts: datetime.datetime

    model_config = {"from_attributes": True}
