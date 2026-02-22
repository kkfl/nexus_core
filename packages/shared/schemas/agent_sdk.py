from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime

class PersonaBlock(BaseModel):
    id: str
    name: str
    version: str
    system_prompt: str
    tools_policy: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None

class AgentTaskMetadata(BaseModel):
    attempt: int
    correlation_id: str
    requested_at: datetime
    timeout_seconds: int

class AgentTaskRequest(BaseModel):
    task_id: str
    type: str
    payload: Dict[str, Any]
    persona: Optional[PersonaBlock] = None
    metadata: AgentTaskMetadata
    context: Optional[List[Dict[str, Any]]] = None

class AgentTaskError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class AgentArtifact(BaseModel):
    kind: str
    content_type: str
    bytes_base64: str
    filename: Optional[str] = None

class ProposedWrite(BaseModel):
    entity_kind: str
    external_ref: Optional[str] = None
    action: str
    patch: Dict[str, Any]
    full_state: Optional[Dict[str, Any]] = None
    idempotency_key: str

class ProposedTask(BaseModel):
    type: str
    priority: str
    payload: Dict[str, Any]
    persona_version_id: Optional[int] = None
    idempotency_key: str

class JobSummary(BaseModel):
    kind: str
    status: str
    details: Optional[Dict[str, Any]] = None

class AgentTaskResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[AgentTaskError] = None
    artifacts: Optional[List[AgentArtifact]] = None
    logs_text: Optional[str] = None
    proposed_writes: Optional[List[ProposedWrite]] = None
    proposed_tasks: Optional[List[ProposedTask]] = None
    job_summary: Optional[JobSummary] = None
