import uuid
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

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
    input: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 30
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    depends_on: List[str] = Field(default_factory=list)

class WorkflowSpec(BaseModel):
    steps: List[WorkflowStep]

# -----------------------------------------------------------------------------
# API Schemas 
# -----------------------------------------------------------------------------

class AutomationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    tenant_id: str
    env: str
    schedule_cron: Optional[str] = None
    enabled: bool = True
    workflow_spec: WorkflowSpec
    max_concurrent_runs: int = 1
    notify_on_failure: bool = True
    notify_on_success: bool = False

class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_cron: Optional[str] = None
    enabled: Optional[bool] = None
    workflow_spec: Optional[WorkflowSpec] = None
    max_concurrent_runs: Optional[int] = None
    notify_on_failure: Optional[bool] = None
    notify_on_success: Optional[bool] = None

class AutomationOut(AutomationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime
    
class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    automation_id: Optional[str] = None
    tenant_id: str
    env: str
    status: str
    idempotency_key: str
    correlation_id: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error_summary: Optional[str] = None

class AutomationStepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    step_id: str
    status: str
    target_agent: str
    attempt: int
    output_summary: Optional[Dict[str, Any]] = None
    last_error_redacted: Optional[str] = None
    duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

class TriggerRunRequest(BaseModel):
    idempotency_key: str
    correlation_id: Optional[str] = None
    tenant_id: Optional[str] = None
    env: Optional[str] = "prod"
    # if providing inputs for templating overrides:
    inputs: Dict[str, Any] = Field(default_factory=dict)
