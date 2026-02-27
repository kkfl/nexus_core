"""
email_agent — admin endpoints (SSH bridge to mx).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.client.ssh_bridge import run_bridge_command
from apps.email_agent.config import config
from apps.email_agent.schemas import (
    AddAliasRequest,
    AdminResponse,
    CreateMailboxRequest,
    DisableMailboxRequest,
    MailboxInfo,
    MailboxStats,
    MailboxWithStats,
    ServerStats,
    SetPasswordRequest,
)
from apps.email_agent.services.mailbox_stats import get_bulk_stats, get_mailbox_stats
from apps.email_agent.services.server_stats import get_server_stats

router = APIRouter(prefix="/email/admin", tags=["admin"])


@router.get("/mailbox/list", response_model=list[MailboxInfo] | list[MailboxWithStats])
async def list_mailboxes(
    include_stats: bool = Query(False, alias="include_stats"),
    _identity: str = Depends(verify_service_identity),
):
    """List all mailboxes via SSH bridge. Optionally include stats."""
    result = await run_bridge_command("list_mailboxes")
    if not isinstance(result, list):
        return []

    mailboxes = [MailboxInfo(**m) for m in result]

    if not include_stats:
        return mailboxes

    # Fetch stats for all mailboxes (uses cache)
    stats_list = await get_bulk_stats([{"email": m.email, "quota": m.quota} for m in mailboxes])
    stats_by_email = {s["email"]: s for s in stats_list}

    enriched = []
    for m in mailboxes:
        s = stats_by_email.get(m.email, {})
        enriched.append(
            MailboxWithStats(
                **m.model_dump(),
                used_mb=s.get("used_mb", 0),
                used_pct=s.get("used_pct", 0),
                free_pct=s.get("free_pct", 100),
                unread_count=s.get("unread_count", 0),
                total_count=s.get("total_count", 0),
                last_received_at=s.get("last_received_at"),
                readable=config.is_mailbox_readable(m.email),
            )
        )
    return enriched


@router.get("/mailbox/{email_addr}/stats", response_model=MailboxStats)
async def mailbox_stats(
    email_addr: str,
    _identity: str = Depends(verify_service_identity),
):
    """Get stats for a single mailbox."""
    stats = await get_mailbox_stats(email_addr)
    return MailboxStats(**stats)


@router.get("/server/stats", response_model=ServerStats)
async def server_stats(
    _identity: str = Depends(verify_service_identity),
):
    """Get server-level postfix queue stats (read-only)."""
    stats = await get_server_stats()
    return ServerStats(**stats)


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
