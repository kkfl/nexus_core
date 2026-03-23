"""
Service Integrations models.

Kept in a separate module from core.py to avoid pulling in pgvector
(which not all micro-agents have installed).
"""

import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from packages.shared.db import Base


class ServiceIntegration(Base):
    """Registered external service that authenticates with Nexus via API key."""

    __tablename__ = "service_integrations"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)
    name: Mapped[str]
    service_id: Mapped[str] = mapped_column(unique=True, index=True)
    api_key_hash: Mapped[str]  # SHA-256 of the API key
    api_key_prefix: Mapped[str]  # First 12 chars for display
    description: Mapped[str | None] = mapped_column(type_=Text)
    permissions: Mapped[list[str]] = mapped_column(type_=JSON, default=list)
    alias_pattern: Mapped[str] = mapped_column(default="*")
    rate_limit_rpm: Mapped[int | None]
    daily_request_limit: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ServiceUsageLog(Base):
    """Usage log entry for service integration API requests."""

    __tablename__ = "service_usage_log"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)
    service_id: Mapped[str] = mapped_column(index=True)
    endpoint: Mapped[str]
    method: Mapped[str]
    status_code: Mapped[int | None]
    ip_address: Mapped[str | None]
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ServicePermissionRule(Base):
    """Scoped permission rule granting a service access to a specific resource."""

    __tablename__ = "service_permission_rules"

    id: Mapped[str] = mapped_column(primary_key=True, index=True)
    service_integration_id: Mapped[str] = mapped_column(
        ForeignKey("service_integrations.id", ondelete="CASCADE"), index=True
    )
    resource_type: Mapped[str]  # secrets, storage, llm, kb
    resource_pattern: Mapped[str] = mapped_column(default="*")  # glob pattern
    actions: Mapped[list[str]] = mapped_column(type_=JSON, default=list)  # read, write, list, etc.
    rate_limit_rpm: Mapped[int | None]
    daily_limit: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
