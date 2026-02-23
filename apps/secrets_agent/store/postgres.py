"""
Secret Store — abstract interface + Postgres implementation.

This abstraction allows swapping the backend (e.g., HashiCorp Vault,
AWS Secrets Manager) without changing business logic.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.crypto.envelope import EncryptedSecret, encrypt_secret, decrypt_secret
from apps.secrets_agent.models import VaultSecret
from apps.secrets_agent.schemas import SecretCreate, SecretUpdate


class AbstractSecretStore(ABC):
    @abstractmethod
    async def create(self, db: AsyncSession, payload: SecretCreate, service_id: str) -> VaultSecret: ...

    @abstractmethod
    async def get(self, db: AsyncSession, secret_id: str) -> Optional[VaultSecret]: ...

    @abstractmethod
    async def get_by_alias(self, db: AsyncSession, alias: str, tenant_id: str, env: str) -> Optional[VaultSecret]: ...

    @abstractmethod
    async def list(self, db: AsyncSession, tenant_id: Optional[str] = None, env: Optional[str] = None,
                   active_only: bool = True, skip: int = 0, limit: int = 50) -> List[VaultSecret]: ...

    @abstractmethod
    async def update(self, db: AsyncSession, secret: VaultSecret, payload: SecretUpdate) -> VaultSecret: ...

    @abstractmethod
    async def deactivate(self, db: AsyncSession, secret: VaultSecret) -> VaultSecret: ...

    @abstractmethod
    async def get_plaintext(self, db: AsyncSession, secret: VaultSecret) -> str: ...


class PostgresSecretStore(AbstractSecretStore):
    """Postgres-backed store using SQLAlchemy async sessions."""

    async def create(self, db: AsyncSession, payload: SecretCreate, service_id: str) -> VaultSecret:
        enc = encrypt_secret(payload.value)
        secret = VaultSecret(
            id=str(uuid.uuid4()),
            alias=payload.alias,
            tenant_id=payload.tenant_id,
            env=payload.env,
            description=payload.description,
            scope_tags=payload.scope_tags or [],
            encrypted_dek=enc.encrypted_dek,
            ciphertext=enc.ciphertext,
            key_version=enc.key_version,
            rotation_interval_days=payload.rotation_interval_days,
            created_by_service_id=service_id,
            is_active=True,
        )
        db.add(secret)
        await db.flush()
        return secret

    async def get(self, db: AsyncSession, secret_id: str) -> Optional[VaultSecret]:
        result = await db.execute(select(VaultSecret).where(VaultSecret.id == secret_id))
        return result.scalars().first()

    async def get_by_alias(self, db: AsyncSession, alias: str, tenant_id: str, env: str) -> Optional[VaultSecret]:
        result = await db.execute(
            select(VaultSecret).where(
                VaultSecret.alias == alias,
                VaultSecret.tenant_id == tenant_id,
                VaultSecret.env == env,
                VaultSecret.is_active.is_(True),
            )
        )
        return result.scalars().first()

    async def list(self, db: AsyncSession, tenant_id: Optional[str] = None, env: Optional[str] = None,
                   active_only: bool = True, skip: int = 0, limit: int = 50) -> List[VaultSecret]:
        q = select(VaultSecret)
        if tenant_id:
            q = q.where(VaultSecret.tenant_id == tenant_id)
        if env:
            q = q.where(VaultSecret.env == env)
        if active_only:
            q = q.where(VaultSecret.is_active.is_(True))
        q = q.order_by(VaultSecret.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    async def update(self, db: AsyncSession, secret: VaultSecret, payload: SecretUpdate) -> VaultSecret:
        if payload.description is not None:
            secret.description = payload.description
        if payload.scope_tags is not None:
            secret.scope_tags = payload.scope_tags
        if payload.rotation_interval_days is not None:
            secret.rotation_interval_days = payload.rotation_interval_days
        if payload.is_active is not None:
            secret.is_active = payload.is_active
        await db.flush()
        return secret

    async def deactivate(self, db: AsyncSession, secret: VaultSecret) -> VaultSecret:
        secret.is_active = False
        await db.flush()
        return secret

    async def get_plaintext(self, db: AsyncSession, secret: VaultSecret) -> str:
        """
        Decrypt and return the plaintext value.
        CALLER RESPONSIBILITY: Never log the returned value.
        """
        enc = EncryptedSecret(
            encrypted_dek=secret.encrypted_dek,
            ciphertext=secret.ciphertext,
            key_version=secret.key_version,
        )
        return decrypt_secret(enc)
