"""
Pydantic schemas for the Secrets Vault API.

INVARIANT: SecretReadResponse is the ONLY schema that includes a value field.
All other schemas deal in metadata only — alias, tenant, env, etc.
Values must never appear in list/get/create responses.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class SecretMeta(BaseModel):
    """Metadata-only view of a secret. No value field."""
    id: str
    alias: str
    tenant_id: str
    env: str
    description: Optional[str] = None
    scope_tags: Optional[List[Any]] = None
    key_version: int
    rotation_interval_days: Optional[int] = None
    last_rotated_at: Optional[datetime.datetime] = None
    next_due_at: Optional[datetime.datetime] = None
    created_by_service_id: str
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Secret lifecycle
# ---------------------------------------------------------------------------

class SecretCreate(BaseModel):
    alias: str = Field(..., min_length=1, max_length=255,
                       pattern=r"^[a-z0-9._\-/]+$",
                       description="Dot/slash/hyphen separated alias e.g. pbx.sip.trunk.password")
    tenant_id: str = Field(..., min_length=1, max_length=128)
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    value: str = Field(..., min_length=1, description="Plaintext secret value (encrypted at rest immediately)")
    description: Optional[str] = Field(None, max_length=500)
    scope_tags: Optional[List[Any]] = None
    rotation_interval_days: Optional[int] = Field(None, ge=1)


class SecretUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=500)
    scope_tags: Optional[Dict[str, Any]] = None
    rotation_interval_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class SecretReadRequest(BaseModel):
    """Body for POST /v1/secrets/{id}/read"""
    reason: Optional[str] = Field(None, max_length=500,
                                   description="Why this secret is being read (for audit log)")


class SecretReadResponse(BaseModel):
    """
    THE ONLY response that includes a secret value.
    This endpoint is separately audited. Treat this value as sensitive.
    """
    id: str
    alias: str
    tenant_id: str
    env: str
    value: str   # plaintext — treat with care
    retrieved_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class SecretRotateRequest(BaseModel):
    new_value: str = Field(..., min_length=1, description="New plaintext secret value")
    reason: Optional[str] = Field(None, max_length=500)


class SecretRotateResponse(BaseModel):
    id: str
    alias: str
    rotated_at: datetime.datetime
    key_version: int


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

class PolicyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    service_id: str = Field(..., max_length=128,
                            description="Exact service ID or glob pattern e.g. 'pbx-agent' or '*'")
    alias_pattern: str = Field(..., max_length=255,
                               description="Glob pattern e.g. 'pbx.*' or '*'")
    tenant_id: Optional[str] = Field(None, max_length=128,
                                      description="None = all tenants")
    env: Optional[str] = Field(None, pattern=r"^(dev|stage|prod)$",
                                description="None = all environments")
    actions: List[str] = Field(..., description="Allowed actions: read|write|rotate|list_metadata|delete")
    priority: int = Field(100, ge=1, le=1000)

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: List[str]) -> List[str]:
        valid = {"read", "write", "rotate", "list_metadata", "delete"}
        bad = set(v) - valid
        if bad:
            raise ValueError(f"Invalid actions: {bad}. Must be subset of {valid}")
        return v


class PolicyOut(BaseModel):
    id: str
    name: str
    service_id: str
    alias_pattern: str
    tenant_id: Optional[str]
    env: Optional[str]
    actions: List[str]
    priority: int
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEventOut(BaseModel):
    id: str
    request_id: str
    service_id: str
    tenant_id: str
    env: str
    secret_alias: str
    action: str
    result: str
    reason: Optional[str]
    ip_address: Optional[str]
    ts: datetime.datetime

    model_config = {"from_attributes": True}


class AuditQueryParams(BaseModel):
    service_id: Optional[str] = None
    tenant_id: Optional[str] = None
    env: Optional[str] = None
    secret_alias: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
