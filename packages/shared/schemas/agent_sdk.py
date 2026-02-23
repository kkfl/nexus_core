from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PersonaBlock(BaseModel):
    id: str
    name: str
    version: str
    system_prompt: str
    tools_policy: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class AgentTaskMetadata(BaseModel):
    attempt: int
    correlation_id: str
    requested_at: datetime
    timeout_seconds: int


class AgentTaskRequest(BaseModel):
    task_id: str
    type: str
    payload: dict[str, Any]
    persona: PersonaBlock | None = None
    metadata: AgentTaskMetadata
    context: list[dict[str, Any]] | None = None


class AgentTaskError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class AgentArtifact(BaseModel):
    kind: str
    content_type: str
    bytes_base64: str
    filename: str | None = None


class ProposedWrite(BaseModel):
    entity_kind: str
    external_ref: str | None = None
    action: str
    patch: dict[str, Any]
    full_state: dict[str, Any] | None = None
    idempotency_key: str


class ProposedTask(BaseModel):
    type: str
    priority: str
    payload: dict[str, Any]
    persona_version_id: int | None = None
    idempotency_key: str


class JobSummary(BaseModel):
    kind: str
    status: str
    details: dict[str, Any] | None = None


class AgentTaskResponse(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    error: AgentTaskError | None = None
    artifacts: list[AgentArtifact] | None = None
    logs_text: str | None = None
    proposed_writes: list[ProposedWrite] | None = None
    proposed_tasks: list[ProposedTask] | None = None
    job_summary: JobSummary | None = None
