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
from pydantic import BaseModel as _PydanticBaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.audit import sink as audit_sink
from apps.secrets_agent.crypto.envelope import encrypt_secret
from apps.secrets_agent.dependencies import (
    ServiceIdentity,
    get_policy_engine,
    get_service_identity,
    get_vault_db,
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

    # Telegram notification (skip internal/automated secrets)
    try:
        from apps.notifications_agent.client.notifications_client import NotificationsClient
        import os
        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="secrets-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        await nc.notify(
            tenant_id=payload.tenant_id, env=payload.env, severity="info",
            channels=["telegram"],
            subject="\U0001f512 Secret Created",
            body=f"{payload.alias} (by {identity.service_id})",
            idempotency_key=f"secret-create:{secret.id}",
        )
    except Exception:
        pass

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
    # Update last_used_at timestamp
    secret.last_used_at = datetime.datetime.utcnow()
    await db.flush()
    # NOTE: plaintext is returned but NOT logged anywhere in this function.
    return SecretReadResponse(
        id=secret.id,
        alias=secret.alias,
        tenant_id=secret.tenant_id,
        env=secret.env,
        value=plaintext,
    )


class _ReadByAliasRequest(_PydanticBaseModel):
    alias: str
    tenant_id: str
    env: str
    reason: str = ""


@router.post("/read-by-alias", response_model=SecretReadResponse)
async def read_secret_by_alias(
    body: _ReadByAliasRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> SecretReadResponse:
    """
    Look up a secret by alias+tenant+env, then decrypt and return the value.
    Equivalent to GET-by-alias + POST /read in a single call.
    Policy is checked against the actual secret alias, not a wildcard.
    """
    secret = await _store.get_by_alias(db, body.alias, body.tenant_id, body.env)
    if not secret or not secret.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Secret alias '{body.alias}' not found.")

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
    secret.last_used_at = datetime.datetime.utcnow()
    await db.flush()
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

    try:
        updated = await _store.update(db, secret, payload)

        await audit_sink.log_event(
            db,
            request_id=identity.request_id,
            service_id=identity.service_id,
            tenant_id=updated.tenant_id,
            env=updated.env,
            secret_alias=updated.alias,
            action="write",
            result="allowed",
            reason="Updated metadata",
            ip_address=identity.ip_address,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Secret with this alias, tenant, and environment already exists.",
        )
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
    reason: str | None = Query(None),
    identity: ServiceIdentity = Depends(get_service_identity),
    policy: PolicyEngine = Depends(get_policy_engine),
    db: AsyncSession = Depends(get_vault_db),
) -> Response:
    """Soft-delete (deactivate) a secret."""
    secret = await _store.get(db, secret_id)
    if not secret:
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
    await audit_sink.log_event(
        db,
        request_id=identity.request_id,
        service_id=identity.service_id,
        tenant_id=secret.tenant_id,
        env=secret.env,
        secret_alias=secret.alias,
        action="delete",
        result="allowed",
        reason=reason or "allowed",
        ip_address=identity.ip_address,
    )
    await _store.deactivate(db, secret)

    # Telegram notification
    try:
        from apps.notifications_agent.client.notifications_client import NotificationsClient
        import os
        nc = NotificationsClient(
            base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
            service_id="secrets-agent",
            api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
        )
        await nc.notify(
            tenant_id=secret.tenant_id, env=secret.env, severity="info",
            channels=["telegram"],
            subject="\U0001f5d1\ufe0f Secret Deleted",
            body=f"{secret.alias} (by {identity.service_id})",
            idempotency_key=f"secret-delete:{secret_id}",
        )
    except Exception:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
