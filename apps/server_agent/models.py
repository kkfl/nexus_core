"""
SQLAlchemy models for the Server Agent.

Tables (all prefixed server_):
  server_hosts          -- provider connection registry
  server_instances      -- tracked VMs/VPS instances
  server_snapshots      -- instance snapshots
  server_backups        -- instance backups
  server_change_jobs    -- async job tracking for mutations
  server_audit_events   -- immutable audit trail (no secrets ever stored)
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class ServerBase(DeclarativeBase):
    pass


class ServerHost(ServerBase):
    """Provider connection registry -- one entry per provider account/cluster."""

    __tablename__ = "server_hosts"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False, index=True)
    provider: str = Column(String(64), nullable=False)  # "vultr" | "proxmox"
    label: str = Column(String(255), nullable=False)
    config: dict = Column(JSONB, nullable=False, default=dict)
    is_active: bool = Column(Boolean, nullable=False, default=True)
    secret_alias: str = Column(String(255), nullable=False)
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())

    instances = relationship("ServerInstance", back_populates="host", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uq_server_hosts_tenant_env_label", "tenant_id", "env", "label", unique=True),
    )


class ServerInstance(ServerBase):
    """Tracked VM/VPS instance -- source of truth for Nexus."""

    __tablename__ = "server_instances"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    host_id: str = Column(
        String(36), ForeignKey("server_hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False, index=True)
    provider: str = Column(String(64), nullable=False)  # denormalized
    provider_instance_id: str = Column(String(255), nullable=False)
    label: str = Column(String(255), nullable=False)
    hostname: str = Column(String(255))
    os: str = Column(String(128))
    plan: str = Column(String(128))
    region: str = Column(String(128))
    ip_v4: str = Column(String(45))
    ip_v6: str = Column(String(128))
    status: str = Column(String(32), nullable=False, default="pending")
    power_status: str = Column(String(32), default="off")
    vcpu_count: int = Column(Integer)
    ram_mb: int = Column(Integer)
    disk_gb: int = Column(Integer)
    tags: dict = Column(JSONB, default=dict)
    last_synced_at: datetime.datetime = Column(DateTime(timezone=True))
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    host = relationship("ServerHost", back_populates="instances")
    snapshots = relationship(
        "ServerSnapshot", back_populates="instance", cascade="all, delete-orphan"
    )
    backups = relationship("ServerBackup", back_populates="instance", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uq_server_inst_host_provider_id", "host_id", "provider_instance_id", unique=True),
        Index("ix_server_inst_tenant_env", "tenant_id", "env"),
    )


class ServerSnapshot(ServerBase):
    """Instance snapshot."""

    __tablename__ = "server_snapshots"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id: str = Column(
        String(36),
        ForeignKey("server_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_snapshot_id: str = Column(String(255))
    name: str = Column(String(255), nullable=False)
    description: str = Column(Text, default="")
    size_gb: float = Column(Float)
    status: str = Column(String(32), nullable=False, default="pending")
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())

    instance = relationship("ServerInstance", back_populates="snapshots")


class ServerBackup(ServerBase):
    """Instance backup."""

    __tablename__ = "server_backups"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id: str = Column(
        String(36),
        ForeignKey("server_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_backup_id: str = Column(String(255))
    backup_type: str = Column(String(32), nullable=False, default="manual")
    size_gb: float = Column(Float)
    status: str = Column(String(32), nullable=False, default="pending")
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())

    instance = relationship("ServerInstance", back_populates="backups")


class ServerChangeJob(ServerBase):
    """Async change job -- tracks lifecycle of server mutations."""

    __tablename__ = "server_change_jobs"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False)
    instance_id: str = Column(
        String(36), ForeignKey("server_instances.id", ondelete="SET NULL"), nullable=True
    )
    operation: str = Column(String(64), nullable=False)
    payload: dict = Column(JSONB, nullable=False, default=dict)
    status: str = Column(String(32), nullable=False, default="pending", index=True)
    attempts: int = Column(Integer, nullable=False, default=0)
    last_error: str = Column(Text)  # NEVER include credential values
    started_at: datetime.datetime = Column(DateTime(timezone=True))
    completed_at: datetime.datetime = Column(DateTime(timezone=True))
    created_by_service_id: str = Column(String(128), nullable=False)
    correlation_id: str = Column(String(64), index=True)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ServerAuditEvent(ServerBase):
    """Immutable audit trail -- every server operation is logged here."""

    __tablename__ = "server_audit_events"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: str = Column(String(64), nullable=False, index=True)
    service_id: str = Column(String(128), nullable=False, index=True)
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False)
    action: str = Column(String(64), nullable=False)
    instance_label: str = Column(String(255))
    provider: str = Column(String(64))
    result: str = Column(String(32), nullable=False)  # success|error|denied
    reason: str = Column(Text)
    ip_address: str = Column(String(64))
    ts: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_server_audit_ts_service", "ts", "service_id"),)
