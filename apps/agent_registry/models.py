"""
SQLAlchemy models for agent_registry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now(UTC)


class RegistryAgent(Base):
    __tablename__ = "registry_agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="active")
    description = Column(Text, nullable=True)
    owner = Column(String(128), nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=_now)

    deployments = relationship(
        "RegistryDeployment", back_populates="agent", cascade="all, delete-orphan"
    )
    capabilities = relationship(
        "RegistryCapability", back_populates="agent", cascade="all, delete-orphan"
    )


class RegistryDeployment(Base):
    __tablename__ = "registry_deployments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(
        String(36), ForeignKey("registry_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id = Column(String(128), nullable=True, index=True)
    env = Column(String(32), nullable=False, index=True)

    base_url = Column(String(256), nullable=False)
    public_url = Column(String(256), nullable=True)
    version = Column(String(64), nullable=True)
    build_sha = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)

    health_endpoint = Column(String(256), nullable=True)
    ready_endpoint = Column(String(256), nullable=True)
    capabilities_endpoint = Column(String(256), nullable=True)

    auth_scheme = Column(String(32), nullable=False, default="headers")
    auth_secret_alias = Column(String(128), nullable=True)
    required_headers = Column(JSONB, nullable=True)
    rate_limits = Column(JSONB, nullable=True)
    timeouts = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=_now)

    agent = relationship("RegistryAgent", back_populates="deployments")


class RegistryCapability(Base):
    __tablename__ = "registry_capabilities"
    __table_args__ = (UniqueConstraint("agent_id", "name", "version", name="uq_reg_cap"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(
        String(36), ForeignKey("registry_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(128), nullable=False)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)

    input_schema = Column(JSONB, nullable=True)
    output_schema = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=_now)

    agent = relationship("RegistryAgent", back_populates="capabilities")


class RegistryAuditEvent(Base):
    __tablename__ = "registry_audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id = Column(String(128), nullable=False, index=True)
    service_id = Column(String(128), nullable=False)
    tenant_id = Column(String(128), nullable=True, index=True)
    env = Column(String(32), nullable=True, index=True)
    action = Column(String(64), nullable=False)
    result = Column(String(16), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
