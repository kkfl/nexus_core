"""
SQLAlchemy models for notifications_agent.
6 tables: notification_jobs, notification_deliveries, notification_templates,
          notification_routing_rules, notification_audit_events
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint,
    ForeignKey, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now(timezone.utc)


class NotificationJob(Base):
    __tablename__ = "notification_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False, index=True)
    env = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)          # info/warn/error/critical
    template_id = Column(String(128), nullable=True)
    subject = Column(Text, nullable=True)
    body_hash = Column(String(64), nullable=False)          # sha256 of rendered body
    body_stored = Column(Text, nullable=True)               # null if sensitivity=sensitive
    sensitivity = Column(String(16), nullable=False, default="normal")
    channels = Column(ARRAY(String), nullable=False)
    routing_rule_id = Column(String(36), nullable=True)
    context = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    max_attempts = Column(Integer, nullable=False, default=3)
    idempotency_key = Column(String(256), nullable=False, unique=True)
    idempotency_expires_at = Column(DateTime(timezone=True), nullable=False)
    correlation_id = Column(String(128), nullable=False)
    created_by_service_id = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    deliveries = relationship("NotificationDelivery", back_populates="job", lazy="selectin")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("notification_jobs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    destination_hash = Column(String(64), nullable=False)   # sha256 of phone/email/chat_id
    status = Column(String(16), nullable=False, default="pending")
    provider_msg_id = Column(String(256), nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    error_code = Column(String(64), nullable=True)
    error_detail_redacted = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    job = relationship("NotificationJob", back_populates="deliveries")


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(String(128), primary_key=True)  # slug e.g. "agent_down"
    name = Column(String(256), nullable=False)
    channel = Column(String(32), nullable=False)  # telegram/email/sms/webhook/all
    subject_template = Column(Text, nullable=True)
    body_template = Column(Text, nullable=False)
    storage_policy = Column(String(16), nullable=False, default="store")  # store/hash_only
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=_now)


class NotificationRoutingRule(Base):
    __tablename__ = "notification_routing_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "env", "severity", name="uq_routing"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False)
    env = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)     # info/warn/error/critical or *
    channels = Column(ARRAY(String), nullable=False)
    config = Column(JSONB, nullable=True)             # webhook_url, chat_id overrides, etc.
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class NotificationAuditEvent(Base):
    __tablename__ = "notification_audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id = Column(String(128), nullable=False, index=True)
    service_id = Column(String(128), nullable=False)
    tenant_id = Column(String(128), nullable=False, index=True)
    env = Column(String(32), nullable=False)
    action = Column(String(64), nullable=False)         # notify/deliver/replay/deny
    job_id = Column(String(36), nullable=True)
    delivery_id = Column(String(36), nullable=True)
    channel = Column(String(32), nullable=True)
    result = Column(String(16), nullable=False)         # ok/failed/denied/dedup
    detail = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
