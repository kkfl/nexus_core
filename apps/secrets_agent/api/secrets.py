"""
Secrets router — CRUD + read (decryption) + rotate.

Access control matrix:
  - list/get metadata:   any authenticated service with list_metadata policy
  - create/update:       service with write policy (or admin)
  - read (decrypt):      service with read policy — audited with full detail
  - rotate:              service with rotate policy
  - delete (deactivate): admin only
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.audit import sink as audit_sink
from apps.secrets_agent.crypto.envelope import encrypt_secret
from apps.secrets_agent.dependencies import (
    ServiceIdentity,
    get_policy_engine,
    get_service_identity,
    get_vault_db,
    require_admin,
)
from apps.secrets_agent.models import VaultSecret
from apps.secrets_agent.policy.engine import PolicyEngine
from apps.secrets_agent.schemas import (
    SecretCreate,
    SecretMeta,
    SecretReadRequest,
    SecretReadResponse,
    SecretRotateRequest,
    SecretRotateResponse,
    SecretUpdate,
)
from apps.secrets_agent.store.postgres import PostgresSecretStore

router = APIRouter(prefix="/v1/secrets", tags=["secrets"])
_store = PostgresSecretStore()


def _to_meta(s: VaultSecret) -> SecretMeta:
    return SecretMeta.model_validate(s)


@router.post("", response_model=SecretMeta, status_code=status.HTTP_201_CREATED)
async def create_secret(
    payload: SecretCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretMeta:
    """Create a new secret. Value is envelope-encrypted immediately; plaintext never persisted."""
    decision = policy.check(
        service_id=identity.service_id,
        action="write",
        secret_alias=payload.alias,
        tenant_id=payload.tenant_id,
        env=payload.env,
    )
    await audit_sink.log_event(
        db,
        request_id=identity.request_id,
        service_id=identity.service_id,
        tenant_id=payload.tenant_id,
        env=payload.env,
        secret_alias=payload.alias,
        action="write",
        result="allowed" if decision.allowed else "denied",
        reason=decision.reason,
        ip_address=identity.ip_address,
    )
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    # Check for duplicate alias+tenant+env
    existing = await _store.get_by_alias(db, payload.alias, payload.tenant_id, payload.env)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Secret with alias '{payload.alias}' already exists for tenant={payload.tenant_id} env={payload.env}.",
        )

    secret = await _store.create(db, payload, service_id=identity.service_id)
    return _to_meta(secret)


@router.get("", response_model=list[SecretMeta])
async def list_secrets(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None, pattern="^(dev|stage|prod)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> list[SecretMeta]:
    """List secret metadata. Values are never included."""
    decision = policy.check(
        service_id=identity.service_id,
        action="list_metadata",
        secret_alias="*",
        tenant_id=tenant_id or "*",
        env=env or "*",
    )
    if not decision.allowed and not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    secrets = await _store.list(db, tenant_id=tenant_id, env=env, skip=skip, limit=limit)
    return [_to_meta(s) for s in secrets]


@router.get("/{secret_id}", response_model=SecretMeta)
async def get_secret(
    secret_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretMeta:
    """Get secret metadata. Value not included."""
    secret = await _store.get(db, secret_id)
    if not secret or not secret.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")
    return _to_meta(secret)


@router.post("/{secret_id}/read", response_model=SecretReadResponse)
async def read_secret_value(
    secret_id: str,
    body: SecretReadRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretReadResponse:
    """
    Decrypt and return the secret value.
    This endpoint is the ONLY path where plaintext is returned.
    Every call is audited regardless of result.
    """
    secret = await _store.get(db, secret_id)
    if not secret or not secret.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")

    decision = policy.check(
        service_id=identity.service_id,
        action="read",
        secret_alias=secret.alias,
        tenant_id=secret.tenant_id,
        env=secret.env,
    )
    await audit_sink.log_event(
        db,
        request_id=identity.request_id,
        service_id=identity.service_id,
        tenant_id=secret.tenant_id,
        env=secret.env,
        secret_alias=secret.alias,
        action="read",
        result="allowed" if decision.allowed else "denied",
        reason=body.reason or decision.reason,
        ip_address=identity.ip_address,
    )
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    plaintext = await _store.get_plaintext(db, secret)
    # NOTE: plaintext is returned but NOT logged anywhere in this function.
    return SecretReadResponse(
        id=secret.id,
        alias=secret.alias,
        tenant_id=secret.tenant_id,
        env=secret.env,
        value=plaintext,
    )


@router.patch("/{secret_id}", response_model=SecretMeta)
async def update_secret(
    secret_id: str,
    payload: SecretUpdate,
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretMeta:
    """Update secret metadata (not value). Use /rotate to change the value."""
    secret = await _store.get(db, secret_id)
    if not secret or not secret.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")

    decision = policy.check(
        service_id=identity.service_id,
        action="write",
        secret_alias=secret.alias,
        tenant_id=secret.tenant_id,
        env=secret.env,
    )
    if not decision.allowed and not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    updated = await _store.update(db, secret, payload)
    return _to_meta(updated)


@router.post("/{secret_id}/rotate", response_model=SecretRotateResponse)
async def rotate_secret(
    secret_id: str,
    body: SecretRotateRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretRotateResponse:
    """Re-encrypt the secret with a new DEK and new value."""
    secret = await _store.get(db, secret_id)
    if not secret or not secret.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")

    decision = policy.check(
        service_id=identity.service_id,
        action="rotate",
        secret_alias=secret.alias,
        tenant_id=secret.tenant_id,
        env=secret.env,
    )
    await audit_sink.log_event(
        db,
        request_id=identity.request_id,
        service_id=identity.service_id,
        tenant_id=secret.tenant_id,
        env=secret.env,
        secret_alias=secret.alias,
        action="rotate",
        result="allowed" if decision.allowed else "denied",
        reason=body.reason or decision.reason,
        ip_address=identity.ip_address,
    )
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    enc = encrypt_secret(body.new_value, key_version=secret.key_version)
    secret.encrypted_dek = enc.encrypted_dek
    secret.ciphertext = enc.ciphertext
    now = datetime.datetime.utcnow()
    secret.last_rotated_at = now
    if secret.rotation_interval_days:
        secret.next_due_at = now + datetime.timedelta(days=secret.rotation_interval_days)
    await db.flush()
    return SecretRotateResponse(
        id=secret.id, alias=secret.alias, rotated_at=now, key_version=secret.key_version
    )


@router.delete("/{secret_id}")
async def delete_secret(
    secret_id: str,
    identity: ServiceIdentity = Depends(require_admin),
    db: AsyncSession = Depends(get_vault_db),
) -> Response:
    """Soft-delete (deactivate) a secret. Admin only."""
    secret = await _store.get(db, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")
    await audit_sink.log_event(
        db,
        request_id=identity.request_id,
        service_id=identity.service_id,
        tenant_id=secret.tenant_id,
        env=secret.env,
        secret_alias=secret.alias,
        action="delete",
        result="allowed",
        ip_address=identity.ip_address,
    )
    await _store.deactivate(db, secret)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
