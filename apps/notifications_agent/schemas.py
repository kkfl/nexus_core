"""
Pydantic schemas for notifications_agent API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Notify request / response
# ---------------------------------------------------------------------------

class NotifyRequest(BaseModel):
    tenant_id: str
    env: str = "prod"
    severity: str = Field(..., pattern="^(info|warn|error|critical)$")
    channels: Optional[List[str]] = None         # explicit channels
    routing_rule_id: Optional[str] = None        # or resolve via routing rule
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None                   # raw body if no template
    context: Optional[Dict[str, Any]] = None     # template variables
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    correlation_id: Optional[str] = None
    sensitivity: str = Field(default="normal", pattern="^(normal|sensitive)$")
    # per-channel destination overrides (optional)
    destinations: Optional[Dict[str, str]] = None  # e.g. {"email": "ops@example.com"}

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels(cls, v):
        allowed = {"telegram", "email", "sms", "webhook", "slack", "teams"}
        if v:
            for ch in v:
                if ch not in allowed:
                    raise ValueError(f"Unknown channel '{ch}'. Allowed: {allowed}")
        return v


class NotifyResponse(BaseModel):
    job_id: str
    status: str
    message: str
    idempotency_key: str


# ---------------------------------------------------------------------------
# Job / delivery output
# ---------------------------------------------------------------------------

class DeliveryOut(BaseModel):
    id: str
    channel: str
    status: str
    destination_hash: str
    provider_msg_id: Optional[str]
    attempt: int
    error_code: Optional[str]
    sent_at: Optional[datetime]


class JobOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    severity: str
    status: str
    channels: List[str]
    template_id: Optional[str]
    sensitivity: str
    attempts: int
    correlation_id: str
    created_at: datetime
    completed_at: Optional[datetime]
    deliveries: List[DeliveryOut] = []


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TemplateCreate(BaseModel):
    id: str = Field(..., description="slug e.g. 'agent_down'")
    name: str
    channel: str = "all"
    subject_template: Optional[str] = None
    body_template: str
    storage_policy: str = Field(default="store", pattern="^(store|hash_only)$")


class TemplateOut(BaseModel):
    id: str
    name: str
    channel: str
    subject_template: Optional[str]
    body_template: str
    storage_policy: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Routing rules
# ---------------------------------------------------------------------------

class RoutingRuleCreate(BaseModel):
    tenant_id: str
    env: str = "prod"
    severity: str = Field(..., pattern="^(info|warn|error|critical|\\*)$")
    channels: List[str]
    config: Optional[Dict[str, Any]] = None
    enabled: bool = True


class RoutingRuleOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    severity: str
    channels: List[str]
    config: Optional[Dict[str, Any]]
    enabled: bool
    created_at: datetime


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
    job_id: Optional[str]
    channel: Optional[str]
    result: str
    detail: Optional[str]
    created_at: datetime
