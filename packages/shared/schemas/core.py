import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List

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
    last_used_at: Optional[datetime.datetime]
    created_at: datetime.datetime
    key: Optional[str] = None  # Only returned on creation

    class Config:
        from_attributes = True

class AgentCreate(BaseModel):
    name: str
    base_url: str
    auth_type: str = "none"
    capabilities: Optional[Dict[str, Any]] = None
    max_concurrency: int = 2
    timeout_seconds: int = 30

class AgentOut(BaseModel):
    id: int
    name: str
    base_url: str
    auth_type: str
    is_active: bool
    api_key_id: Optional[int]
    capabilities: Optional[Dict[str, Any]]
    created_at: datetime.datetime
    last_seen_at: Optional[datetime.datetime]
    status: str
    max_concurrency: int
    timeout_seconds: int

    class Config:
        from_attributes = True

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    capabilities: Optional[Dict[str, Any]] = None
    max_concurrency: Optional[int] = None
    timeout_seconds: Optional[int] = None

class PersonaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class PersonaOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class PersonaVersionCreate(BaseModel):
    version: str
    system_prompt: str
    tools_policy: Optional[Dict[str, Any]] = None
    meta_data: Optional[Dict[str, Any]] = None

class PersonaVersionOut(BaseModel):
    id: int
    persona_id: int
    version: str
    system_prompt: str
    tools_policy: Optional[Dict[str, Any]]
    meta_data: Optional[Dict[str, Any]]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class TaskCreate(BaseModel):
    type: str
    payload: Dict[str, Any]
    assigned_agent_id: Optional[int] = None
    persona_version_id: Optional[int] = None
    priority: int = 1

class TaskOut(BaseModel):
    id: int
    type: str
    status: str
    priority: int
    payload: Dict[str, Any]
    persona_version_id: Optional[int]
    requested_by_user_id: Optional[int]
    assigned_agent_id: Optional[int]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None

class TokenData(BaseModel):
    username: Optional[str] = None

class AgentCheckinCreate(BaseModel):
    status: str
    meta_data: Optional[Dict[str, Any]] = None

class AgentCheckinOut(BaseModel):
    id: int
    agent_id: int
    status: str
    meta_data: Optional[Dict[str, Any]]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class TaskRouteCreate(BaseModel):
    task_type: str
    required_capabilities: List[str]
    preferred_agent_id: Optional[int] = None
    is_active: bool = True

class TaskRouteUpdate(BaseModel):
    required_capabilities: Optional[List[str]] = None
    preferred_agent_id: Optional[int] = None
    is_active: Optional[bool] = None

class TaskRouteOut(BaseModel):
    id: int
    task_type: str
    required_capabilities: List[str]
    preferred_agent_id: Optional[int]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class PersonaDefaultCreate(BaseModel):
    scope_type: str = Field(pattern="^(global|task_type|agent_id)$")
    scope_value: Optional[str] = None
    persona_version_id: int
    is_active: bool = True

class PersonaDefaultUpdate(BaseModel):
    scope_value: Optional[str] = None
    persona_version_id: Optional[int] = None
    is_active: Optional[bool] = None

class PersonaDefaultOut(BaseModel):
    id: int
    scope_type: str
    scope_value: Optional[str]
    persona_version_id: int
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True
