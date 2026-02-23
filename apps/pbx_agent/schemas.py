"""
Pydantic v2 schemas for pbx_agent request/response validation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ─── PBX Target ──────────────────────────────────────────────────────────────

class PbxTargetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    tenant_id: str
    env: str
    host: str = Field(..., max_length=256)
    ami_port: int = 5038
    ami_username: str = Field(..., max_length=128)
    ami_secret_alias: str = Field(..., max_length=255, description="Alias key in secrets-agent, e.g. pbx.target1.ami.secret")
    status: str = "active"
    metadata: Optional[Dict[str, Any]] = None

class PbxTargetUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    ami_port: Optional[int] = None
    ami_username: Optional[str] = None
    ami_secret_alias: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

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
    correlation_id: Optional[str] = None


# ─── Jobs ────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    tenant_id: str
    env: str = "prod"
    pbx_target_id: str
    action: str = Field(..., description="One of: reload")
    correlation_id: Optional[str] = None

class PbxJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    env: str
    pbx_target_id: Optional[str] = None
    action: str
    status: str
    attempts: int
    correlation_id: str
    created_at: datetime

class PbxJobResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: str
    output_summary: Optional[Dict[str, Any]] = None
    error_redacted: Optional[str] = None
    duration_ms: Optional[int] = None
    completed_at: datetime

class PbxJobDetailOut(PbxJobOut):
    result: Optional[PbxJobResultOut] = None


# ─── Audit ───────────────────────────────────────────────────────────────────

class PbxAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    correlation_id: str
    service_id: str
    tenant_id: Optional[str] = None
    env: Optional[str] = None
    action: str
    target_id: Optional[str] = None
    result: str
    detail: Optional[str] = None
    created_at: datetime
