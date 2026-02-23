"""
SQLAlchemy models for the DNS Agent.

Tables (all prefixed dns_):
  dns_zones         — tenant+env zone registrations
  dns_records       — desired record state (source of truth)
  dns_change_jobs   — async job tracking for mutations
  dns_audit_events  — immutable audit trail (no secret values ever stored)
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class DnsBase(DeclarativeBase):
    pass


class DnsZone(DnsBase):
    """
    A DNS zone managed for a tenant/env pair.
    One zone belongs to exactly one DNS provider.
    """
    __tablename__ = "dns_zones"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False, index=True)
    zone_name: str = Column(String(255), nullable=False)
    provider: str = Column(String(64), nullable=False)     # "cloudflare" | "dnsmadeeasy"
    provider_zone_id: str = Column(String(255))            # provider's internal zone ID
    is_active: bool = Column(Boolean, nullable=False, default=True)
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    records = relationship("DnsRecord", back_populates="zone", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uq_dns_zones_tenant_env_zone", "tenant_id", "env", "zone_name", unique=True),
    )


class DnsRecord(DnsBase):
    """
    Desired DNS record state — the source of truth for Nexus.
    provider_record_id tracks the record in the provider's system.
    """
    __tablename__ = "dns_records"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    zone_id: str = Column(String(36), ForeignKey("dns_zones.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False, index=True)
    record_type: str = Column(String(16), nullable=False)   # A, AAAA, CNAME, MX, TXT, SRV, PTR
    name: str = Column(String(255), nullable=False)         # e.g. "@", "api", "mail"
    value: str = Column(Text, nullable=False)
    ttl: int = Column(Integer, nullable=False, default=300)
    priority: int = Column(Integer)                         # for MX, SRV
    tags: dict = Column(JSONB, default=dict)
    provider_record_id: str = Column(String(255))           # provider's record ID
    last_synced_at: datetime.datetime = Column(DateTime(timezone=True))
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone = relationship("DnsZone", back_populates="records")

    __table_args__ = (
        Index("uq_dns_records_zone_type_name", "zone_id", "record_type", "name", unique=True),
        Index("ix_dns_records_tenant_env", "tenant_id", "env"),
    )


class DnsChangeJob(DnsBase):
    """
    Async change job — tracks lifecycle of mutations to DNS records.
    Status: pending → running → succeeded | failed
    """
    __tablename__ = "dns_change_jobs"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False)
    zone_name: str = Column(String(255), nullable=False)
    operation: str = Column(String(64), nullable=False)     # upsert|delete|sync|ensure_zone
    payload: dict = Column(JSONB, nullable=False, default=dict)
    status: str = Column(String(32), nullable=False, default="pending", index=True)
    attempts: int = Column(Integer, nullable=False, default=0)
    last_error: str = Column(Text)                          # NEVER include credential values
    started_at: datetime.datetime = Column(DateTime(timezone=True))
    completed_at: datetime.datetime = Column(DateTime(timezone=True))
    created_by_service_id: str = Column(String(128), nullable=False)
    correlation_id: str = Column(String(64), index=True)
    created_at: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class DnsAuditEvent(DnsBase):
    """
    Immutable audit trail — every DNS operation is logged here.
    Secret values are NEVER stored here.
    """
    __tablename__ = "dns_audit_events"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id: str = Column(String(64), nullable=False, index=True)
    service_id: str = Column(String(128), nullable=False, index=True)
    tenant_id: str = Column(String(128), nullable=False, index=True)
    env: str = Column(String(32), nullable=False)
    action: str = Column(String(64), nullable=False)        # create_zone|upsert_record|delete_record|sync|etc.
    zone_name: str = Column(String(255))
    record_type: str = Column(String(16))
    record_name: str = Column(String(255))
    result: str = Column(String(32), nullable=False)        # success|error|denied
    reason: str = Column(Text)
    ip_address: str = Column(String(64))
    ts: datetime.datetime = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_dns_audit_ts_service", "ts", "service_id"),
    )
