"""
SQLAlchemy ORM models for pbx_agent.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class PbxTarget(Base):
    """Registered PBX system — stores connection config + secret aliases (never secrets)."""
    __tablename__ = "pbx_targets"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(128), nullable=False, index=True)
    env = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    host = Column(String(256), nullable=False)
    ami_port = Column(Integer, nullable=False, default=5038)
    ami_username = Column(String(128), nullable=False)          # plaintext username, not secret
    ami_secret_alias = Column(String(255), nullable=False)      # e.g. pbx.target1.ami.secret
    status = Column(String(32), nullable=False, default="active")
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    jobs = relationship("PbxJob", back_populates="target", lazy="noload")


class PbxJob(Base):
    """DB-backed job queue for mutating PBX actions (reload, etc.)."""
    __tablename__ = "pbx_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(128), nullable=False, index=True)
    env = Column(String(64), nullable=False)
    pbx_target_id = Column(String(36), ForeignKey("pbx_targets.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(128), nullable=False)                   # e.g. "reload", "status.peers"
    payload_redacted = Column(JSONB, nullable=True)               # input with secrets stripped
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(128), nullable=False, default=_uuid)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    target = relationship("PbxTarget", back_populates="jobs", lazy="noload")
    result = relationship("PbxJobResult", back_populates="job", uselist=False, lazy="noload")


class PbxJobResult(Base):
    """Stored result for a completed (or failed) job."""
    __tablename__ = "pbx_job_results"

    job_id = Column(String(36), ForeignKey("pbx_jobs.id", ondelete="CASCADE"), primary_key=True)
    output_summary = Column(JSONB, nullable=True)
    error_redacted = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    job = relationship("PbxJob", back_populates="result", lazy="noload")


class PbxAuditEvent(Base):
    """Immutable audit log — who called what, when, with what result."""
    __tablename__ = "pbx_audit_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    correlation_id = Column(String(128), nullable=False, index=True)
    service_id = Column(String(128), nullable=False)
    tenant_id = Column(String(128), nullable=True, index=True)
    env = Column(String(64), nullable=True)
    action = Column(String(128), nullable=False)
    target_id = Column(String(36), nullable=True)
    result = Column(String(32), nullable=False)      # success / denied / error
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
