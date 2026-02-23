from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# Workflow Definition Schema
# -----------------------------------------------------------------------------
class RetryPolicy(BaseModel):
    max_attempts: int = 3
    backoff_ms: int = 1000


class WorkflowStep(BaseModel):
    step_id: str
    agent_name: str
    action: str  # e.g., "POST /v1/records"
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 30
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    depends_on: list[str] = Field(default_factory=list)


class WorkflowSpec(BaseModel):
    steps: list[WorkflowStep]


# -----------------------------------------------------------------------------
# API Schemas
# -----------------------------------------------------------------------------


class AutomationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    tenant_id: str
    env: str
    schedule_cron: str | None = None
    enabled: bool = True
    workflow_spec: WorkflowSpec
    max_concurrent_runs: int = 1
    notify_on_failure: bool = True
    notify_on_success: bool = False


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule_cron: str | None = None
    enabled: bool | None = None
    workflow_spec: WorkflowSpec | None = None
    max_concurrent_runs: int | None = None
    notify_on_failure: bool | None = None
    notify_on_success: bool | None = None


class AutomationOut(AutomationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    automation_id: str | None = None
    tenant_id: str
    env: str
    status: str
    idempotency_key: str
    correlation_id: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_summary: str | None = None


class AutomationStepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    step_id: str
    status: str
    target_agent: str
    attempt: int
    output_summary: dict[str, Any] | None = None
    last_error_redacted: str | None = None
    duration_ms: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class TriggerRunRequest(BaseModel):
    idempotency_key: str
    correlation_id: str | None = None
    tenant_id: str | None = None
    env: str | None = "prod"
    # if providing inputs for templating overrides:
    inputs: dict[str, Any] = Field(default_factory=dict)
