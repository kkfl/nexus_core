import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ApiKeyCreate(BaseModel):
    owner_type: str = Field(pattern="^(user|agent)$")
    owner_id: int
    name: str


class ApiKeyOut(BaseModel):
    id: int
    owner_type: str
    owner_id: int
    name: str
    last_used_at: datetime.datetime | None
    created_at: datetime.datetime
    key: str | None = None  # Only returned on creation

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    name: str
    base_url: str
    auth_type: str = "none"
    capabilities: dict[str, Any] | None = None
    max_concurrency: int = 2
    timeout_seconds: int = 30


class AgentOut(BaseModel):
    id: int
    name: str
    base_url: str
    auth_type: str
    is_active: bool
    api_key_id: int | None
    capabilities: dict[str, Any] | None
    created_at: datetime.datetime
    last_seen_at: datetime.datetime | None
    status: str
    max_concurrency: int
    timeout_seconds: int

    class Config:
        from_attributes = True


class AgentUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    is_active: bool | None = None
    capabilities: dict[str, Any] | None = None
    max_concurrency: int | None = None
    timeout_seconds: int | None = None


class PersonaCreate(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class PersonaOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PersonaVersionCreate(BaseModel):
    version: str
    system_prompt: str
    tools_policy: dict[str, Any] | None = None
    meta_data: dict[str, Any] | None = None


class PersonaVersionOut(BaseModel):
    id: int
    persona_id: int
    version: str
    system_prompt: str
    tools_policy: dict[str, Any] | None
    meta_data: dict[str, Any] | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    type: str
    payload: dict[str, Any]
    assigned_agent_id: int | None = None
    persona_version_id: int | None = None
    priority: int = 1


class TaskOut(BaseModel):
    id: int
    type: str
    status: str
    priority: int
    payload: dict[str, Any]
    persona_version_id: int | None
    requested_by_user_id: int | None
    assigned_agent_id: int | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str | None = None


class TokenData(BaseModel):
    username: str | None = None


class AgentCheckinCreate(BaseModel):
    status: str
    meta_data: dict[str, Any] | None = None


class AgentCheckinOut(BaseModel):
    id: int
    agent_id: int
    status: str
    meta_data: dict[str, Any] | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TaskRouteCreate(BaseModel):
    task_type: str
    required_capabilities: list[str]
    preferred_agent_id: int | None = None
    is_active: bool = True


class TaskRouteUpdate(BaseModel):
    required_capabilities: list[str] | None = None
    preferred_agent_id: int | None = None
    is_active: bool | None = None


class TaskRouteOut(BaseModel):
    id: int
    task_type: str
    required_capabilities: list[str]
    preferred_agent_id: int | None
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PersonaDefaultCreate(BaseModel):
    scope_type: str = Field(pattern="^(global|task_type|agent_id)$")
    scope_value: str | None = None
    persona_version_id: int
    is_active: bool = True


class PersonaDefaultUpdate(BaseModel):
    scope_value: str | None = None
    persona_version_id: int | None = None
    is_active: bool | None = None


class PersonaDefaultOut(BaseModel):
    id: int
    scope_type: str
    scope_value: str | None
    persona_version_id: int
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True
