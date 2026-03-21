"""
Pydantic v2 schemas for pbx_agent request/response validation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    # SSH access (for system metrics + asterisk CLI)
    ssh_port: int = 22
    ssh_username: str = "root"
    ssh_key_alias: str | None = Field(
        None, max_length=255, description="Vault alias for SSH private key PEM"
    )
    ssh_password_alias: str | None = Field(
        None, max_length=255, description="Vault alias for SSH password (fallback)"
    )
    status: str = "active"
    metadata: dict[str, Any] | None = None


class PbxTargetUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    ami_port: int | None = None
    ami_username: str | None = None
    ami_secret_alias: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_key_alias: str | None = None
    ssh_password_alias: str | None = None
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
    ssh_port: int = 22
    ssh_username: str = "root"
    ssh_key_alias: str | None = None
    ssh_password_alias: str | None = None
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


# ─── Fleet Status ────────────────────────────────────────────────────────────


class PbxFleetNodeOut(BaseModel):
    """Combined AMI + SSH metrics for a single PBX."""

    target_id: str
    name: str
    host: str
    status: str  # active/disabled from DB

    # Connectivity
    online: bool = False
    ssh_ok: bool = False
    ami_ok: bool = False

    # Asterisk (from AMI or SSH CLI)
    asterisk_up: bool = False
    asterisk_version: str | None = None
    sip_registrations: int = 0
    active_calls: int = 0
    calls_24h: int = 0
    uptime_seconds: int = 0
    uptime_human: str | None = None  # e.g. "14d 3h 22m"

    # System resources (from SSH)
    cpu_pct: float | None = None
    ram_used_mb: int | None = None
    ram_total_mb: int | None = None
    ram_pct: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    disk_pct: float | None = None

    # Polling metadata
    last_polled_at: datetime | None = None
    poll_error: str | None = None


class PbxFleetSummaryOut(BaseModel):
    """Aggregate fleet-level stats."""

    total_targets: int = 0
    online: int = 0
    offline: int = 0
    asterisk_up: int = 0
    asterisk_down: int = 0
    total_active_calls: int = 0
    total_calls_24h: int = 0
    total_registrations: int = 0
    avg_cpu_pct: float | None = None
    avg_ram_pct: float | None = None
    avg_disk_pct: float | None = None
    last_polled_at: datetime | None = None


class PbxFleetStatusOut(BaseModel):
    """Full fleet status response."""

    nodes: list[PbxFleetNodeOut] = []
    summary: PbxFleetSummaryOut = PbxFleetSummaryOut()
    refreshing: bool = False
    collected_at: datetime | None = None


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


# ─── Register + Verify ────────────────────────────────────────────────────────


def _sanitize_pem_key(v: str | None) -> str | None:
    """Clean up a pasted PEM key: strip \\r, trailing spaces, and normalise line endings."""
    if not v:
        return v
    # Strip carriage returns (Windows line endings)
    v = v.replace('\r\n', '\n').replace('\r', '\n')
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in v.split('\n')]
    # Remove any blank lines in the middle of the key (but keep header/footer)
    cleaned = []
    for line in lines:
        if line:  # skip blank lines
            cleaned.append(line)
    return '\n'.join(cleaned) + '\n'



class PbxTargetRegister(BaseModel):
    """Registration request that accepts raw credentials (not vault aliases)."""
    name: str = Field(..., max_length=255)
    tenant_id: str = "acme"
    env: str = "prod"
    host: str = Field(..., max_length=256)
    ami_port: int = 5038
    ami_username: str = Field(..., max_length=128)
    ami_secret: str = Field(..., description="Raw AMI secret/password")
    ssh_port: int = 22
    ssh_username: str = "root"
    ssh_key_pem: str | None = Field(None, description="Raw SSH private key PEM")
    ssh_password: str | None = Field(None, description="Raw SSH password (fallback)")

    @field_validator('ssh_key_pem', mode='before')
    @classmethod
    def clean_ssh_key(cls, v: str | None) -> str | None:
        return _sanitize_pem_key(v)


class PbxTargetEdit(BaseModel):
    """Edit request — all fields optional. Credential fields (if provided) are re-stored in vault."""
    name: str | None = None
    host: str | None = None
    ami_port: int | None = None
    ami_username: str | None = None
    ami_secret: str | None = Field(None, description="New AMI secret — leave blank to keep existing")
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_key_pem: str | None = Field(None, description="New SSH key PEM — leave blank to keep existing")
    ssh_password: str | None = Field(None, description="New SSH password — leave blank to keep existing")

    @field_validator('ssh_key_pem', mode='before')
    @classmethod
    def clean_ssh_key(cls, v: str | None) -> str | None:
        return _sanitize_pem_key(v)


class VerifyCheckResult(BaseModel):
    check: str
    passed: bool
    detail: str | None = None


class PbxRegistrationResult(BaseModel):
    target_id: str | None = None
    target_name: str
    registered: bool
    checks: list[VerifyCheckResult]
    error: str | None = None
