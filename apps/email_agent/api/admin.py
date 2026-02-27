"""
email_agent — admin endpoints (SSH bridge to mx).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

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
    ServerStats,
    SetPasswordRequest,
)
from apps.email_agent.services.mailbox_stats import (
    get_bulk_stats_cached,
    get_mailbox_stats,
    refresh_stats,
)
from apps.email_agent.services.server_stats import get_server_stats

router = APIRouter(prefix="/email/admin", tags=["admin"])


@router.get("/mailbox/list", response_model=list[MailboxInfo])
async def list_mailboxes(
    _identity: str = Depends(verify_service_identity),
):
    """List all mailboxes via SSH bridge (fast, no stats)."""
    result = await run_bridge_command("list_mailboxes")
    if isinstance(result, list):
        return [MailboxInfo(**m) for m in result]
    return []


@router.get("/mailbox/stats/bulk")
async def bulk_stats(
    _identity: str = Depends(verify_service_identity),
):
    """
    Return cached bulk mailbox stats.
    If stale, triggers background refresh and returns cached data + refreshing flag.
    """
    result = await get_bulk_stats_cached()
    # Add readable flag per mailbox
    for s in result.get("stats", []):
        s["readable"] = config.is_mailbox_readable(s.get("email", ""))
    return result


@router.post("/mailbox/stats/refresh")
async def trigger_refresh(
    _identity: str = Depends(verify_service_identity),
):
    """Force-refresh mailbox stats now (admin only, blocking)."""
    stats, error = await refresh_stats()
    return {"ok": error is None, "count": len(stats), "error": error}


@router.get("/mailbox/{email_addr}/stats", response_model=MailboxStats)
async def mailbox_stats(
    email_addr: str,
    _identity: str = Depends(verify_service_identity),
):
    """Get stats for a single mailbox (from cache)."""
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
