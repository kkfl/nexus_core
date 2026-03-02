"""
Vault SQLAlchemy models.

All vault tables are prefixed `vault_` to clearly scope them within the
shared Nexus Postgres instance and avoid collision with core Nexus tables.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class VaultBase(DeclarativeBase):
    """Separate declarative base so vault models don't mix into Nexus models."""

    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class VaultSecret(VaultBase):
    """
    Encrypted secret stored in the vault.

    INVARIANT: encrypted_dek and ciphertext are always set together.
    plaintext NEVER appears in this table.
    """

    __tablename__ = "vault_secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alias: Mapped[str] = mapped_column(String(255), index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    env: Mapped[str] = mapped_column(String(32), index=True)  # dev|stage|prod
    description: Mapped[str | None] = mapped_column(Text)
    scope_tags: Mapped[dict[str, Any] | None] = mapped_column(JSON, server_default="[]")

    # Envelope encryption
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1)

    # Rotation metadata
    rotation_interval_days: Mapped[int | None] = mapped_column(Integer)
    last_rotated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_service_id: Mapped[str] = mapped_column(String(128), default="system")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("alias", "tenant_id", "env", name="uq_vault_secrets_alias_tenant_env"),
        Index("ix_vault_secrets_tenant_env", "tenant_id", "env"),
    )


class VaultPolicy(VaultBase):
    """
    Access control policy for the vault.

    service_id: exact match or glob pattern (e.g. "pbx-agent", "*")
    alias_pattern: glob pattern matched against secret.alias
    actions: JSON list of allowed actions: ["read", "list_metadata", "write", "rotate"]
    Default deny: only explicit matches grant access.
    """

    __tablename__ = "vault_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    service_id: Mapped[str] = mapped_column(String(128))  # exact or glob
    alias_pattern: Mapped[str] = mapped_column(String(255))  # glob
    tenant_id: Mapped[str | None] = mapped_column(String(128))  # None = all tenants
    env: Mapped[str | None] = mapped_column(String(32))  # None = all envs
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # higher = evaluated first
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VaultAuditEvent(VaultBase):
    """
    Immutable audit log for every secret access attempt.

    INVARIANT: secret values MUST NEVER appear in any field of this table.
    alias is stored (metadata), value is never stored.
    """

    __tablename__ = "vault_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    service_id: Mapped[str] = mapped_column(String(128), index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    env: Mapped[str] = mapped_column(String(32))
    secret_alias: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64))  # read|write|rotate|list_metadata|delete
    result: Mapped[str] = mapped_column(String(32))  # allowed|denied|error
    reason: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (Index("ix_vault_audit_ts_service", "ts", "service_id"),)


class VaultLease(VaultBase):
    """
    Short-lived access grants (V1: informational — enables future TTL enforcement).
    """

    __tablename__ = "vault_leases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    secret_id: Mapped[str] = mapped_column(String(36), index=True)
    service_id: Mapped[str] = mapped_column(String(128))
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
