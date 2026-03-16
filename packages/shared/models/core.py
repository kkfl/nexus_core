import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from packages.shared.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    refresh_token_hash: Mapped[str | None]
    role: Mapped[str] = mapped_column(default="reader")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_type: Mapped[str]  # 'user' or 'agent'
    owner_id: Mapped[int]
    key_hash: Mapped[str]
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    last_used_at: Mapped[datetime.datetime | None]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())



class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str]
    base_url: Mapped[str]
    auth_type: Mapped[str] = mapped_column(default="none")
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    # New fields for Agent Integration
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="unknown")  # unknown|healthy|unreachable|disabled
    max_concurrency: Mapped[int] = mapped_column(default=2)
    timeout_seconds: Mapped[int] = mapped_column(default=30)


class AgentCheckin(Base):
    __tablename__ = "agent_checkins"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str]
    description: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    versions = relationship("PersonaVersion", back_populates="persona")


class PersonaVersion(Base):
    __tablename__ = "persona_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"))
    version: Mapped[str]
    system_prompt: Mapped[str] = mapped_column(type_=Text)
    tools_policy: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    persona = relationship("Persona", back_populates="versions")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    type: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    priority: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(type_=JSON)

    persona_version_id: Mapped[int | None] = mapped_column(ForeignKey("persona_versions.id"))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_by_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))

    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    attempt: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="running")
    started_at: Mapped[datetime.datetime | None]
    finished_at: Mapped[datetime.datetime | None]
    error_text: Mapped[str | None] = mapped_column(type_=Text)
    logs_object_key: Mapped[str | None]


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str]
    storage_backend: Mapped[str]
    object_key: Mapped[str]
    content_type: Mapped[str]
    byte_size: Mapped[int]
    checksum: Mapped[str | None]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    actor_type: Mapped[str]
    actor_id: Mapped[int]
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[int]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(type_=JSON)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class VectorMeta(Base):
    __tablename__ = "vectors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    namespace: Mapped[str] = mapped_column(index=True)
    source_type: Mapped[str]
    source_id: Mapped[int]
    embedding = mapped_column(Vector(1536))
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class TaskRoute(Base):
    __tablename__ = "task_routes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_type: Mapped[str] = mapped_column(unique=True, index=True)
    required_capabilities: Mapped[list[str]] = mapped_column(type_=JSON)
    preferred_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    is_active: Mapped[bool] = mapped_column(default=True)

    # RAG routing rules
    needs_rag: Mapped[bool] = mapped_column(default=False)
    rag_namespaces: Mapped[list[str] | None] = mapped_column(type_=JSON)
    rag_top_k: Mapped[int | None]

    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class PersonaDefault(Base):
    __tablename__ = "persona_defaults"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scope_type: Mapped[str]  # 'global'|'task_type'|'agent_id'
    scope_value: Mapped[str | None]
    persona_version_id: Mapped[int] = mapped_column(ForeignKey("persona_versions.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class KbSource(Base):
    __tablename__ = "kb_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)
    kind: Mapped[str]
    config: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("kb_sources.id"))
    namespace: Mapped[str] = mapped_column(index=True)
    title: Mapped[str]
    content_type: Mapped[str]
    storage_backend: Mapped[str]
    object_key: Mapped[str]
    bytes_size: Mapped[int]
    checksum: Mapped[str | None]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    ingest_status: Mapped[str] = mapped_column(default="uploaded")
    error_message: Mapped[str | None] = mapped_column(type_=Text)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id"))
    chunk_index: Mapped[int]
    text_content: Mapped[str] = mapped_column(type_=Text)
    char_count: Mapped[int]
    token_count: Mapped[int | None]
    start_char: Mapped[int | None]
    end_char: Mapped[int | None]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class KbEmbedding(Base):
    __tablename__ = "kb_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("kb_chunks.id"), unique=True)
    # Using dim=384 for fastembed default models (e.g. BAAI/bge-small-en-v1.5)
    embedding = mapped_column(Vector(384))
    model: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class KbAccessLog(Base):
    __tablename__ = "kb_access_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    actor_type: Mapped[str]
    actor_id: Mapped[int]
    query_text: Mapped[str] = mapped_column(type_=Text)
    namespaces: Mapped[list[str]] = mapped_column(type_=JSON)
    top_k: Mapped[int]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    name: Mapped[str] = mapped_column(unique=True, index=True)
    owner_type: Mapped[str]  # 'global', 'agent', 'user'
    owner_id: Mapped[int | None]
    purpose: Mapped[str]
    ciphertext: Mapped[LargeBinary] = mapped_column(type_=LargeBinary)
    key_version: Mapped[int]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    kind: Mapped[str] = mapped_column(index=True)
    external_ref: Mapped[str | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="active")
    data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class EntityEvent(Base):
    __tablename__ = "entity_events"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    actor_type: Mapped[str]  # 'user'|'agent'|'system'
    actor_id: Mapped[str | None]  # uuid string
    action: Mapped[str]
    before: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    diff: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    correlation_id: Mapped[str | None]
    idempotency_key: Mapped[str | None] = mapped_column(index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    key: Mapped[str] = mapped_column(unique=True, index=True)
    scope: Mapped[str]
    request_hash: Mapped[str]
    response: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime.datetime]


class TaskLink(Base):
    __tablename__ = "task_links"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    rel: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class PbxTarget(Base):
    __tablename__ = "pbx_targets"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    name: Mapped[str] = mapped_column(unique=True, index=True)
    description: Mapped[str | None]
    ami_host: Mapped[str]
    ami_port: Mapped[int] = mapped_column(default=5038)
    ami_username: Mapped[str]
    ami_secret_secret_id: Mapped[str] = mapped_column(ForeignKey("secrets.id"))
    ami_use_tls: Mapped[bool] = mapped_column(default=False)
    tags: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON, server_default="[]")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class PbxSnapshot(Base):
    __tablename__ = "pbx_snapshots"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    pbx_target_id: Mapped[str] = mapped_column(ForeignKey("pbx_targets.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[str]  # created|succeeded|failed
    summary: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class MonitoringSource(Base):
    __tablename__ = "monitoring_sources"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    name: Mapped[str] = mapped_column(unique=True, index=True)
    kind: Mapped[str] = mapped_column(default="nagios")
    base_url: Mapped[str | None]
    auth_secret_id: Mapped[str | None] = mapped_column(ForeignKey("secrets.id"))
    tags: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON, server_default="[]")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class MonitoringIngest(Base):
    __tablename__ = "monitoring_ingests"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    monitoring_source_id: Mapped[str] = mapped_column(ForeignKey("monitoring_sources.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    received_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    summary: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class StorageTarget(Base):
    __tablename__ = "storage_targets"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    name: Mapped[str] = mapped_column(unique=True, index=True)
    description: Mapped[str | None]
    kind: Mapped[str] = mapped_column(default="s3")
    endpoint_url: Mapped[str]
    region: Mapped[str | None]
    bucket: Mapped[str]
    access_key_id_secret_id: Mapped[str] = mapped_column(ForeignKey("secrets.id"))
    secret_access_key_secret_id: Mapped[str] = mapped_column(ForeignKey("secrets.id"))
    base_prefix: Mapped[str] = mapped_column(default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    tags: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON, server_default="[]")
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class StorageJob(Base):
    __tablename__ = "storage_jobs"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    storage_target_id: Mapped[str] = mapped_column(ForeignKey("storage_targets.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    kind: Mapped[str]  # copy|lifecycle_propose|lifecycle_apply|delete
    status: Mapped[str]  # created|running|succeeded|failed
    summary: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class CarrierTarget(Base):
    __tablename__ = "carrier_targets"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    name: Mapped[str] = mapped_column(unique=True, index=True)
    provider: Mapped[str] = mapped_column(default="mock")  # twilio|telnyx|skyetel|bulkvs|mock
    base_url: Mapped[str | None]
    api_key_secret_id: Mapped[str | None] = mapped_column(ForeignKey("secrets.id"))
    api_secret_secret_id: Mapped[str | None] = mapped_column(ForeignKey("secrets.id"))
    tags: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON, server_default="[]")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class CarrierSnapshot(Base):
    __tablename__ = "carrier_snapshots"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # UUID string
    carrier_target_id: Mapped[str] = mapped_column(ForeignKey("carrier_targets.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[str]  # created|succeeded|failed
    summary: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class MetricEvent(Base):
    __tablename__ = "metrics_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(index=True)
    value: Mapped[float | None]
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now(), index=True)


class BusEvent(Base):
    """Persistent event store for the Nexus event bus (audit + replay)."""

    __tablename__ = "bus_events"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)  # event_id UUID
    event_type: Mapped[str] = mapped_column(index=True)
    event_version: Mapped[int] = mapped_column(default=1)
    occurred_at: Mapped[str]  # ISO 8601 string
    produced_by: Mapped[str] = mapped_column(index=True)
    correlation_id: Mapped[str | None] = mapped_column(index=True)
    causation_id: Mapped[str | None]
    actor_type: Mapped[str | None]
    actor_id: Mapped[str | None]
    tenant_id: Mapped[str | None] = mapped_column(index=True)
    severity: Mapped[str] = mapped_column(default="info")
    tags: Mapped[list[str] | None] = mapped_column(type_=JSON)
    payload: Mapped[dict[str, Any] | None] = mapped_column(type_=JSON)
    payload_schema_version: Mapped[int] = mapped_column(default=1)
    idempotency_key: Mapped[str | None] = mapped_column(index=True)
    stream_id: Mapped[str | None]  # Redis Stream entry ID
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now(), index=True)


class AskFeedback(Base):
    __tablename__ = "ask_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    correlation_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    rating: Mapped[str]  # "good" | "bad"
    note: Mapped[str | None]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class IpAllowlistEntry(Base):
    """IP allowlist entry. When entries exist, only matching IPs can access the API."""

    __tablename__ = "ip_allowlist"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cidr: Mapped[str]  # e.g. '10.0.0.0/8' or '1.2.3.4/32'
    label: Mapped[str]  # human-readable label, e.g. 'Office VPN'
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

