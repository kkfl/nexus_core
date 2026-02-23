import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Integer, DateTime, JSON, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from apps.automation_agent.store.database import Base

def gen_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)


class Automation(Base):
    __tablename__ = "automation_definitions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    tenant_id = Column(String(128), nullable=False)
    env = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    schedule_cron = Column(String(255), nullable=True) # e.g. "0 * * * *"
    enabled = Column(Boolean, nullable=False, default=True)
    workflow_spec = Column(JSONB, nullable=False)
    max_concurrent_runs = Column(Integer, nullable=False, default=1)
    notify_on_failure = Column(Boolean, nullable=False, default=True)
    notify_on_success = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    runs = relationship("AutomationRun", back_populates="automation", cascade="all, delete-orphan")


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    automation_id = Column(String(36), ForeignKey("automation_definitions.id", ondelete="SET NULL"), nullable=True)
    tenant_id = Column(String(128), nullable=False)
    env = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False) # pending, running, succeeded, failed
    idempotency_key = Column(String(255), nullable=False, unique=True)
    correlation_id = Column(String(128), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    error_summary = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    automation = relationship("Automation", back_populates="runs")
    steps = relationship("AutomationStepRun", back_populates="run", cascade="all, delete-orphan", order_by="AutomationStepRun.created_at")
    dlq_entry = relationship("AutomationDLQ", back_populates="run", uselist=False, cascade="all, delete-orphan")


class AutomationStepRun(Base):
    __tablename__ = "automation_step_runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    run_id = Column(String(36), ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False) # pending, running, succeeded, failed, skipped
    target_agent = Column(String(128), nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    output_summary = Column(JSONB, nullable=True)
    last_error_redacted = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("AutomationRun", back_populates="steps")


class AutomationDLQ(Base):
    __tablename__ = "automation_dlq"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    run_id = Column(String(36), ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    failed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    replay_count = Column(Integer, nullable=False, default=0)
    last_replay_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("AutomationRun", back_populates="dlq_entry")


class AutomationAuditEvent(Base):
    __tablename__ = "automation_audit_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    correlation_id = Column(String(128), nullable=False)
    service_id = Column(String(128), nullable=False)
    tenant_id = Column(String(128), nullable=True)
    env = Column(String(64), nullable=True)
    action = Column(String(128), nullable=False)
    automation_id = Column(String(36), nullable=True)
    run_id = Column(String(36), nullable=True)
    result = Column(String(64), nullable=False)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
