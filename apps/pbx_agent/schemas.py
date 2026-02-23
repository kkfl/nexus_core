"""
Pydantic v2 schemas for pbx_agent request/response validation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── PBX Target ──────────────────────────────────────────────────────────────


class PbxTargetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    tenant_id: str
    env: str
    host: str = Field(..., max_length=256)
    ami_port: int = 5038
    ami_username: str = Field(..., max_length=128)
    ami_secret_alias: str = Field(
        ..., max_length=255, description="Alias key in secrets-agent, e.g. pbx.target1.ami.secret"
    )
    status: str = "active"
    metadata: dict[str, Any] | None = None


class PbxTargetUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    ami_port: int | None = None
    ami_username: str | None = None
    ami_secret_alias: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class PbxTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    env: str
    name: str
    host: str
    ami_port: int
    ami_username: str
    ami_secret_alias: str
    status: str
    created_at: datetime
    updated_at: datetime


# ─── Diagnostics / Status requests ───────────────────────────────────────────


class TargetRequest(BaseModel):
    """Minimal request body for any operation requiring a PBX target."""

    tenant_id: str
    env: str = "prod"
    pbx_target_id: str
    correlation_id: str | None = None


# ─── Jobs ────────────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    tenant_id: str
    env: str = "prod"
    pbx_target_id: str
    action: str = Field(..., description="One of: reload")
    correlation_id: str | None = None


class PbxJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    env: str
    pbx_target_id: str | None = None
    action: str
    status: str
    attempts: int
    correlation_id: str
    created_at: datetime


class PbxJobResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: str
    output_summary: dict[str, Any] | None = None
    error_redacted: str | None = None
    duration_ms: int | None = None
    completed_at: datetime


class PbxJobDetailOut(PbxJobOut):
    result: PbxJobResultOut | None = None


# ─── Audit ───────────────────────────────────────────────────────────────────


class PbxAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    correlation_id: str
    service_id: str
    tenant_id: str | None = None
    env: str | None = None
    action: str
    target_id: str | None = None
    result: str
    detail: str | None = None
    created_at: datetime
