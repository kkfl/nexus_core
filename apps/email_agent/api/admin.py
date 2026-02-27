"""
email_agent — admin endpoints (SSH bridge to mx).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.client.ssh_bridge import run_bridge_command
from apps.email_agent.schemas import (
    AddAliasRequest,
    AdminResponse,
    CreateMailboxRequest,
    DisableMailboxRequest,
    MailboxInfo,
    SetPasswordRequest,
)

router = APIRouter(prefix="/email/admin", tags=["admin"])


@router.get("/mailbox/list", response_model=list[MailboxInfo])
async def list_mailboxes(
    _identity: str = Depends(verify_service_identity),
):
    """List all mailboxes via SSH bridge."""
    result = await run_bridge_command("list_mailboxes")
    if isinstance(result, list):
        return [MailboxInfo(**m) for m in result]
    return []


@router.post("/mailbox/create", response_model=AdminResponse)
async def create_mailbox(
    req: CreateMailboxRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Create a new mailbox via SSH bridge."""
    result = await run_bridge_command("create_mailbox", [req.email, req.password])
    return AdminResponse(**result)


@router.post("/mailbox/password", response_model=AdminResponse)
async def set_password(
    req: SetPasswordRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Reset mailbox password via SSH bridge."""
    result = await run_bridge_command("set_password", [req.email, req.password])
    return AdminResponse(**result)


@router.post("/mailbox/disable", response_model=AdminResponse)
async def disable_mailbox(
    req: DisableMailboxRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Disable a mailbox via SSH bridge."""
    result = await run_bridge_command("disable_mailbox", [req.email])
    return AdminResponse(**result)


@router.post("/alias/add", response_model=AdminResponse)
async def add_alias(
    req: AddAliasRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Add a mail alias via SSH bridge."""
    result = await run_bridge_command("add_alias", [req.alias, req.destination])
    return AdminResponse(**result)
