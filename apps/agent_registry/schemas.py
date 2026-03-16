"""
Pydantic schemas for the Agent Registry API.
"""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    status: str = Field("active", pattern=r"^(active|disabled)$")
    description: str | None = None
    owner: str | None = None
    tags: list[str] | None = None


class AgentUpdate(BaseModel):
    status: str | None = Field(None, pattern=r"^(active|disabled)$")
    description: str | None = None
    owner: str | None = None
    tags: list[str] | None = None


class AgentOut(BaseModel):
    id: str
    name: str
    status: str
    description: str | None
    owner: str | None
    tags: list[str] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None
    last_heartbeat: datetime.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Deployment schemas
# ---------------------------------------------------------------------------


class DeploymentCreate(BaseModel):
    agent_id: str
    tenant_id: str | None = None
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    base_url: str = Field(..., min_length=1, max_length=256)
    public_url: str | None = None
    version: str | None = None
    build_sha: str | None = None
    health_endpoint: str | None = "/healthz"
    ready_endpoint: str | None = "/readyz"
    capabilities_endpoint: str | None = None
    auth_scheme: str = Field("headers")
    auth_secret_alias: str | None = None
    required_headers: dict[str, Any] | None = None
    rate_limits: dict[str, Any] | None = None
    timeouts: dict[str, Any] | None = None


class DeploymentUpdate(BaseModel):
    base_url: str | None = None
    public_url: str | None = None
    version: str | None = None
    build_sha: str | None = None
    health_endpoint: str | None = None
    ready_endpoint: str | None = None
    capabilities_endpoint: str | None = None
    auth_scheme: str | None = None
    auth_secret_alias: str | None = None
    required_headers: dict[str, Any] | None = None
    rate_limits: dict[str, Any] | None = None
    timeouts: dict[str, Any] | None = None


class DeploymentOut(BaseModel):
    id: str
    agent_id: str
    tenant_id: str | None
    env: str
    base_url: str
    public_url: str | None
    version: str | None
    build_sha: str | None
    started_at: datetime.datetime | None
    health_endpoint: str | None
    ready_endpoint: str | None
    capabilities_endpoint: str | None
    auth_scheme: str
    auth_secret_alias: str | None
    required_headers: dict[str, Any] | None
    rate_limits: dict[str, Any] | None
    timeouts: dict[str, Any] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Capability schemas
# ---------------------------------------------------------------------------


class CapabilitySpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class CapabilitiesCreate(BaseModel):
    # This allows batch registering capabilities for a given agent
    agent_id: str
    capabilities: list[CapabilitySpec]


class CapabilityOut(BaseModel):
    id: str
    agent_id: str
    name: str
    version: str
    description: str | None
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit Event schemas
# ---------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    id: str
    correlation_id: str
    service_id: str
    tenant_id: str | None
    env: str | None
    action: str
    result: str
    detail: str | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
