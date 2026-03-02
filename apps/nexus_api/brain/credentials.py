"""
Nexus Brain — Credential Controller.

Centralizes all credential provisioning decisions.
The Portal sends raw credentials HERE (never to leaf agents).
Brain stores them in secrets_agent vault, then tells the target agent
to use a vault reference — so raw secrets never travel to leaf agents
over the wire.

Supported credential targets:
  - EMAIL_MAILBOX: mailbox create / password reset on mx.gsmcall.com
  - PBX_AMI: AMI secret for Asterisk PBX targets
  - CARRIER_AUTH: Twilio auth tokens for carrier targets

Design:
  - Follows the same proxy_request pattern as portal_secrets.py
  - Stores credentials in secrets_agent under well-known aliases
  - Passes vault aliases (not raw values) to downstream agents
  - Every operation is audited end-to-end
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

import httpx
import structlog
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from packages.shared.client.agent_registry import get_registry_client

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CredentialAction(str, Enum):
    PROVISION = "provision"
    ROTATE = "rotate"
    REVOKE = "revoke"


class CredentialTarget(str, Enum):
    EMAIL_MAILBOX = "email_mailbox"
    PBX_AMI = "pbx_ami"
    CARRIER_AUTH = "carrier_auth"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EmailCredentialRequest(BaseModel):
    """Portal request to create a mailbox or reset a password."""
    email: str
    password: str = Field(..., min_length=8)
    action: str = Field(..., pattern=r"^(create|reset_password)$")


class EmailCredentialResponse(BaseModel):
    ok: bool
    email: str | None = None
    vault_alias: str | None = None
    action: str | None = None
    error: str | None = None


class PbxCredentialRequest(BaseModel):
    """Portal request to provision or rotate a PBX AMI secret."""
    target_name: str
    ami_secret: str = Field(..., min_length=1)


class PbxCredentialResponse(BaseModel):
    ok: bool
    vault_alias: str | None = None
    error: str | None = None


class CredentialAuditEntry(BaseModel):
    action: str
    target: str
    alias: str
    actor: str
    timestamp: str
    result: str


# ---------------------------------------------------------------------------
# Vault Proxy Helpers (reuses portal_secrets pattern)
# ---------------------------------------------------------------------------

_VAULT_SERVICE_ID = os.environ.get("NEXUS_VAULT_SERVICE_ID", "nexus")
_VAULT_AGENT_KEY = os.environ.get("NEXUS_VAULT_AGENT_KEY", "nexus-internal-key")


async def _get_secrets_agent_url() -> str:
    registry = get_registry_client()
    agent = await registry.resolve_agent("secrets-agent", tenant_id=None, env="prod")
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secrets Agent not available",
        )
    return agent.base_url


async def _vault_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_data: dict[str, Any] | None = None,
) -> Any:
    """Low-level proxy to secrets_agent."""
    base_url = await _get_secrets_agent_url()
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "X-Service-ID": _VAULT_SERVICE_ID,
        "X-Agent-Key": _VAULT_AGENT_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.request(method, url, params=params, json=json_data, headers=headers)
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                raise HTTPException(status_code=resp.status_code, detail=detail)
            return resp.json() if resp.content else None
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error connecting to secrets-agent: {exc}",
            )


# ---------------------------------------------------------------------------
# Vault alias conventions
# ---------------------------------------------------------------------------


def _email_vault_alias(email: str) -> str:
    """Deterministic vault alias for an email mailbox password."""
    safe = email.replace("@", "_at_").replace(".", "_")
    return f"email.mailbox.{safe}.password"


def _pbx_vault_alias(target_name: str) -> str:
    """Deterministic vault alias for a PBX AMI secret."""
    safe = target_name.replace(" ", "_").lower()
    return f"pbx.ami.{safe}.secret"


# ---------------------------------------------------------------------------
# Core Credential Operations
# ---------------------------------------------------------------------------


async def store_credential_in_vault(
    alias: str,
    value: str,
    description: str | None = None,
    tenant_id: str = "nexus",
    env: str = "prod",
) -> dict[str, Any]:
    """
    Store (or rotate) a credential in secrets_agent vault.

    If the alias already exists, rotates the value.
    If it does not exist, creates a new secret.
    """
    # Check if alias exists
    existing = await _vault_request(
        "GET", "/v1/secrets", params={"tenant_id": tenant_id, "env": env}
    )
    matched = next((s for s in (existing or []) if s.get("alias") == alias), None)

    if matched:
        # Rotate existing secret
        logger.info("brain_credential_rotate", alias=alias)
        return await _vault_request(
            "POST",
            f"/v1/secrets/{matched['id']}/rotate",
            json_data={"new_value": value, "reason": "brain_credential_rotate"},
        )
    else:
        # Create new secret
        logger.info("brain_credential_create", alias=alias)
        return await _vault_request(
            "POST",
            "/v1/secrets",
            json_data={
                "alias": alias,
                "tenant_id": tenant_id,
                "env": env,
                "value": value,
                "description": description or f"Brain-managed credential: {alias}",
            },
        )


async def provision_email_credential(
    req: EmailCredentialRequest,
    email_agent_base_url: str,
    email_agent_key: str,
) -> EmailCredentialResponse:
    """
    Handle mailbox create or password reset.
    1. Store password in vault under a deterministic alias
    2. Call email_agent admin endpoint with vault_ref (not raw password)
    """
    alias = _email_vault_alias(req.email)

    # Step 1: Store password in vault
    try:
        await store_credential_in_vault(
            alias=alias,
            value=req.password,
            description=f"Mailbox password for {req.email}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("brain_vault_store_failed", alias=alias, error=str(exc)[:200])
        return EmailCredentialResponse(
            ok=False, email=req.email, error=f"Failed to store credential: {str(exc)[:200]}"
        )

    # Step 2: Call email_agent with vault_ref
    endpoint = "/email/admin/mailbox/create" if req.action == "create" else "/email/admin/mailbox/password"
    payload: dict[str, Any] = {"email": req.email, "vault_ref": alias}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{email_agent_base_url.rstrip('/')}{endpoint}",
                json=payload,
                headers={
                    "X-Service-ID": "nexus",
                    "X-Agent-Key": email_agent_key,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                err = resp.text[:300]
                logger.error("brain_email_agent_call_failed", status=resp.status_code, error=err)
                return EmailCredentialResponse(ok=False, email=req.email, error=err)
            result = resp.json()
            return EmailCredentialResponse(
                ok=result.get("ok", False),
                email=result.get("email", req.email),
                vault_alias=alias,
                action=req.action,
                error=result.get("error"),
            )
    except httpx.RequestError as exc:
        logger.error("brain_email_agent_unreachable", error=str(exc)[:200])
        return EmailCredentialResponse(
            ok=False, email=req.email, error=f"Email agent unreachable: {str(exc)[:200]}"
        )


async def provision_pbx_credential(
    req: PbxCredentialRequest,
) -> PbxCredentialResponse:
    """
    Store PBX AMI secret in vault.
    Returns the vault alias for use when creating/updating PBX targets.
    """
    alias = _pbx_vault_alias(req.target_name)

    try:
        await store_credential_in_vault(
            alias=alias,
            value=req.ami_secret,
            description=f"AMI secret for PBX target: {req.target_name}",
        )
        return PbxCredentialResponse(ok=True, vault_alias=alias)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("brain_pbx_vault_store_failed", alias=alias, error=str(exc)[:200])
        return PbxCredentialResponse(ok=False, error=f"Failed to store credential: {str(exc)[:200]}")
