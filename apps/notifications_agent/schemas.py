"""
Pydantic schemas for notifications_agent API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Notify request / response
# ---------------------------------------------------------------------------


class NotifyRequest(BaseModel):
    tenant_id: str
    env: str = "prod"
    severity: str = Field(..., pattern="^(info|warn|error|critical)$")
    channels: list[str] | None = None  # explicit channels
    routing_rule_id: str | None = None  # or resolve via routing rule
    template_id: str | None = None
    subject: str | None = None
    body: str | None = None  # raw body if no template
    context: dict[str, Any] | None = None  # template variables
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    correlation_id: str | None = None
    sensitivity: str = Field(default="normal", pattern="^(normal|sensitive)$")
    # per-channel destination overrides (optional)
    destinations: dict[str, str] | None = None  # e.g. {"email": "ops@example.com"}

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
    provider_msg_id: str | None
    attempt: int
    error_code: str | None
    sent_at: datetime | None


class JobOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    severity: str
    status: str
    channels: list[str]
    template_id: str | None
    sensitivity: str
    attempts: int
    correlation_id: str
    created_at: datetime
    completed_at: datetime | None
    deliveries: list[DeliveryOut] = []


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    id: str = Field(..., description="slug e.g. 'agent_down'")
    name: str
    channel: str = "all"
    subject_template: str | None = None
    body_template: str
    storage_policy: str = Field(default="store", pattern="^(store|hash_only)$")


class TemplateOut(BaseModel):
    id: str
    name: str
    channel: str
    subject_template: str | None
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
    channels: list[str]
    config: dict[str, Any] | None = None
    enabled: bool = True


class RoutingRuleOut(BaseModel):
    id: str
    tenant_id: str
    env: str
    severity: str
    channels: list[str]
    config: dict[str, Any] | None
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
    job_id: str | None
    channel: str | None
    result: str
    detail: str | None
    created_at: datetime
