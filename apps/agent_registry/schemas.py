"""
Pydantic schemas for the Agent Registry API.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    status: str = Field("active", pattern=r"^(active|disabled)$")
    description: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None


class AgentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(active|disabled)$")
    description: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None


class AgentOut(BaseModel):
    id: str
    name: str
    status: str
    description: Optional[str]
    owner: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Deployment schemas
# ---------------------------------------------------------------------------

class DeploymentCreate(BaseModel):
    agent_id: str
    tenant_id: Optional[str] = None
    env: str = Field(..., pattern=r"^(dev|stage|prod)$")
    base_url: str = Field(..., min_length=1, max_length=256)
    public_url: Optional[str] = None
    version: Optional[str] = None
    build_sha: Optional[str] = None
    health_endpoint: Optional[str] = "/healthz"
    ready_endpoint: Optional[str] = "/readyz"
    capabilities_endpoint: Optional[str] = None
    auth_scheme: str = Field("headers")
    auth_secret_alias: Optional[str] = None
    required_headers: Optional[Dict[str, Any]] = None
    rate_limits: Optional[Dict[str, Any]] = None
    timeouts: Optional[Dict[str, Any]] = None


class DeploymentUpdate(BaseModel):
    base_url: Optional[str] = None
    public_url: Optional[str] = None
    version: Optional[str] = None
    build_sha: Optional[str] = None
    health_endpoint: Optional[str] = None
    ready_endpoint: Optional[str] = None
    capabilities_endpoint: Optional[str] = None
    auth_scheme: Optional[str] = None
    auth_secret_alias: Optional[str] = None
    required_headers: Optional[Dict[str, Any]] = None
    rate_limits: Optional[Dict[str, Any]] = None
    timeouts: Optional[Dict[str, Any]] = None


class DeploymentOut(BaseModel):
    id: str
    agent_id: str
    tenant_id: Optional[str]
    env: str
    base_url: str
    public_url: Optional[str]
    version: Optional[str]
    build_sha: Optional[str]
    started_at: Optional[datetime.datetime]
    health_endpoint: Optional[str]
    ready_endpoint: Optional[str]
    capabilities_endpoint: Optional[str]
    auth_scheme: str
    auth_secret_alias: Optional[str]
    required_headers: Optional[Dict[str, Any]]
    rate_limits: Optional[Dict[str, Any]]
    timeouts: Optional[Dict[str, Any]]
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Capability schemas
# ---------------------------------------------------------------------------

class CapabilitySpec(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


class CapabilitiesCreate(BaseModel):
    # This allows batch registering capabilities for a given agent
    agent_id: str
    capabilities: List[CapabilitySpec]


class CapabilityOut(BaseModel):
    id: str
    agent_id: str
    name: str
    version: str
    description: Optional[str]
    input_schema: Optional[Dict[str, Any]]
    output_schema: Optional[Dict[str, Any]]
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit Event schemas
# ---------------------------------------------------------------------------

class AuditEventOut(BaseModel):
    id: str
    correlation_id: str
    service_id: str
    tenant_id: Optional[str]
    env: Optional[str]
    action: str
    result: str
    detail: Optional[str]
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
