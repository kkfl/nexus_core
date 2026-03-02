"""
Brain routes — Portal-facing API for centralized credential management.

All credential mutations from the Portal flow through these endpoints.
Brain stores credentials in vault first, then delegates to the target agent
with a vault reference (never a raw password).
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, Depends

from apps.nexus_api.brain.credentials import (
    EmailCredentialRequest,
    EmailCredentialResponse,
    PbxCredentialRequest,
    PbxCredentialResponse,
    provision_email_credential,
    provision_pbx_credential,
)
from apps.nexus_api.dependencies import RequireRole
from packages.shared.client.agent_registry import get_registry_client

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Email credential endpoints
# ---------------------------------------------------------------------------


async def _resolve_email_agent() -> tuple[str, str]:
    """Resolve email_agent base_url and auth key."""
    registry = get_registry_client()
    agent = await registry.resolve_agent("email-agent", tenant_id=None, env="prod")
    base_url = agent.base_url if agent else os.environ.get(
        "EMAIL_AGENT_URL", "http://email-agent:8014"
    )
    key = os.environ.get("BRAIN_EMAIL_AGENT_KEY", "nexus-email-key-change-me")
    return base_url, key


@router.post("/credentials/email/mailbox", response_model=EmailCredentialResponse)
async def email_mailbox_credential(
    req: EmailCredentialRequest,
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> EmailCredentialResponse:
    """
    Create a mailbox or reset its password.

    Flow:
    1. Brain stores the password in secrets_agent vault
    2. Brain calls email_agent with a vault_ref (not the raw password)
    3. email_agent resolves the vault_ref and executes via SSH bridge
    """
    base_url, key = await _resolve_email_agent()

    logger.info(
        "brain_email_credential",
        action=req.action,
        email=req.email,
        user=getattr(current_user, "username", "unknown"),
    )

    result = await provision_email_credential(
        req=req,
        email_agent_base_url=base_url,
        email_agent_key=key,
    )

    if result.ok:
        logger.info(
            "brain_email_credential_success",
            action=req.action,
            email=req.email,
            vault_alias=result.vault_alias,
        )
    else:
        logger.warning(
            "brain_email_credential_failed",
            action=req.action,
            email=req.email,
            error=result.error,
        )

    return result


# ---------------------------------------------------------------------------
# PBX credential endpoints
# ---------------------------------------------------------------------------


@router.post("/credentials/pbx/secret", response_model=PbxCredentialResponse)
async def pbx_ami_credential(
    req: PbxCredentialRequest,
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> PbxCredentialResponse:
    """
    Store a PBX AMI secret in vault.

    Returns the vault alias. The caller uses this alias when creating
    or updating a PBX target — the target's ami_secret_secret_id will
    reference this vault entry instead of a locally-encrypted blob.
    """
    logger.info(
        "brain_pbx_credential",
        target_name=req.target_name,
        user=getattr(current_user, "username", "unknown"),
    )

    result = await provision_pbx_credential(req=req)

    if result.ok:
        logger.info(
            "brain_pbx_credential_success",
            target_name=req.target_name,
            vault_alias=result.vault_alias,
        )
    else:
        logger.warning(
            "brain_pbx_credential_failed",
            target_name=req.target_name,
            error=result.error,
        )

    return result


# ---------------------------------------------------------------------------
# Credential audit endpoint
# ---------------------------------------------------------------------------


@router.get("/credentials/audit")
async def credential_audit(
    limit: int = 50,
    offset: int = 0,
    current_user: Any = Depends(RequireRole(["admin", "BreakGlass"])),
) -> Any:
    """
    Return audit log of all Brain credential operations.
    Proxies to secrets_agent audit filtered by brain-managed aliases.
    """
    from apps.nexus_api.brain.credentials import _vault_request

    return await _vault_request(
        "GET",
        "/v1/audit",
        params={
            "service_id": "nexus",
            "limit": limit,
            "offset": offset,
        },
    )
