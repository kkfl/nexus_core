"""
Pydantic schemas for the DNS Agent API.

INVARIANT: No provider credentials appear in any schema.
           No plaintext API tokens, API keys, or secrets.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_VALID_PROVIDERS = {"cloudflare", "dnsmadeeasy"}
_VALID_ENVS = {"dev", "stage", "prod"}
_VALID_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "TXT", "SRV", "PTR", "NS", "CAA"}
_VALID_JOB_STATUSES = {"pending", "running", "succeeded", "failed"}


# ---------------------------------------------------------------------------
# Zone schemas
# ---------------------------------------------------------------------------


class ZoneCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    zone_name: str = Field(..., min_length=3, max_length=255, description="e.g. example.com")
    provider: str = Field(..., description="cloudflare | dnsmadeeasy")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {_VALID_PROVIDERS}")
        return v

    @field_validator("zone_name")
    @classmethod
    def validate_zone_name(cls, v: str) -> str:
        return v.lower().strip(".")


class ZoneOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    zone_name: str
    provider: str
    provider_zone_id: str | None = None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Record schemas
# ---------------------------------------------------------------------------


class RecordSpec(BaseModel):
    """A single DNS record specification."""

    record_type: str = Field(..., description="A|AAAA|CNAME|MX|TXT|SRV|PTR|NS|CAA")
    name: str = Field(
        ..., min_length=1, max_length=255, description="Relative name e.g. '@', 'api', 'mail'"
    )
    value: str = Field(..., min_length=1, description="Record value. Never a credential.")
    ttl: int = Field(300, ge=60, le=86400)
    priority: int | None = Field(None, ge=0, le=65535, description="For MX/SRV only")
    tags: dict[str, Any] | None = None

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str) -> str:
        v = v.upper()
        if v not in _VALID_RECORD_TYPES:
            raise ValueError(f"record_type must be one of {_VALID_RECORD_TYPES}")
        return v

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.lower().strip()


class RecordOut(BaseModel):
    id: str
    zone_id: str
    tenant_id: str
    env: str
    record_type: str
    name: str
    value: str
    ttl: int
    priority: int | None = None
    tags: dict[str, Any] | None = None
    provider_record_id: str | None = None
    last_synced_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Upsert / Delete batch requests
# ---------------------------------------------------------------------------


class BatchUpsertRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    zone: str = Field(..., description="Zone name e.g. example.com")
    records: list[RecordSpec] = Field(..., min_length=1, max_length=100)
    dry_run: bool = Field(False, description="If true, validate but do not apply")

    @field_validator("zone")
    @classmethod
    def normalize_zone(cls, v: str) -> str:
        return v.lower().strip(".")


class BatchDeleteRequest(BaseModel):
    tenant_id: str
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    zone: str
    records: list[RecordSpec] = Field(..., min_length=1)

    @field_validator("zone")
    @classmethod
    def normalize_zone(cls, v: str) -> str:
        return v.lower().strip(".")


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------


class JobOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    zone_name: str
    operation: str
    status: str
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
# Sync
# ---------------------------------------------------------------------------


class SyncRequest(BaseModel):
    tenant_id: str
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    zone: str
    reconcile: bool = Field(False, description="If true, apply drift fixes automatically")


class DriftRecord(BaseModel):
    record_type: str
    name: str
    expected: str | None  # None if record should not exist
    actual: str | None  # None if record does not exist in provider


class SyncResult(BaseModel):
    zone: str
    tenant_id: str
    env: str
    provider: str
    drift_count: int
    drift: list[DriftRecord]
    reconciled: bool
    job_id: str | None = None  # set if reconcile=true


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    id: str
    correlation_id: str
    service_id: str
    tenant_id: str
    env: str
    action: str
    zone_name: str | None
    record_type: str | None
    record_name: str | None
    result: str
    reason: str | None
    ip_address: str | None
    ts: datetime.datetime

    model_config = {"from_attributes": True}
