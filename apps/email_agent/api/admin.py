"""
email_agent — admin endpoints (SSH bridge to mx).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.client import vault
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
from apps.email_agent.services.sent_stats import (
    get_sent_detail,
    get_sent_stats_cached,
    refresh_sent_stats,
)
from apps.email_agent.services.server_stats import get_server_stats

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/email/admin", tags=["admin"])


async def _resolve_password(password: str | None, vault_ref: str | None) -> str:
    """
    Resolve password from either inline value or vault reference.

    Priority: vault_ref > password (vault_ref is the secure Brain-managed path).
    Raises 422 if neither is provided.
    """
    if vault_ref:
        _log.info("resolve_password_from_vault", alias=vault_ref)
        try:
            return await vault.get_secret(vault_ref)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to resolve vault_ref '{vault_ref}': {str(exc)[:200]}",
            )
    if password:
        _log.warning(
            "resolve_password_inline_deprecated",
            msg="Raw password received; use vault_ref via Brain",
        )
        return password
    raise HTTPException(status_code=422, detail="Either 'password' or 'vault_ref' must be provided")


@router.get("/mailbox/list", response_model=list[MailboxInfo])
async def list_mailboxes(
    _identity: str = Depends(verify_service_identity),
):
    """List all mailboxes via SSH bridge (fast, no stats)."""
    result = await run_bridge_command("list_mailboxes")
    if isinstance(result, list):
        return [MailboxInfo(**m) for m in result]

    # If not a list, it's an error dict from the bridge
    err_msg = result.get("error", str(result)) if isinstance(result, dict) else str(result)
    raise HTTPException(status_code=502, detail=f"Mail server connection failed: {err_msg}")


@router.get("/domains")
async def list_domains(
    _identity: str = Depends(verify_service_identity),
):
    """List unique domains with mailbox counts (derived from mailbox list)."""
    result = await run_bridge_command("list_mailboxes")
    if not isinstance(result, list):
        err_msg = result.get("error", str(result)) if isinstance(result, dict) else str(result)
        raise HTTPException(status_code=502, detail=f"Mail server connection failed: {err_msg}")
    domain_map: dict[str, dict] = {}
    for m in result:
        d = m.get("domain", "unknown")
        if d not in domain_map:
            domain_map[d] = {
                "domain": d,
                "mailbox_count": 0,
                "active_count": 0,
                "disabled_count": 0,
            }
        domain_map[d]["mailbox_count"] += 1
        if m.get("active", 0) == 1:
            domain_map[d]["active_count"] += 1
        else:
            domain_map[d]["disabled_count"] += 1
    return sorted(domain_map.values(), key=lambda x: x["domain"])


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
    resolved_pw = await _resolve_password(req.password, req.vault_ref)
    result = await run_bridge_command("create_mailbox", [req.email, resolved_pw])
    return AdminResponse(**result)


@router.post("/mailbox/password", response_model=AdminResponse)
async def set_password(
    req: SetPasswordRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Reset mailbox password via SSH bridge."""
    resolved_pw = await _resolve_password(req.password, req.vault_ref)
    result = await run_bridge_command("set_password", [req.email, resolved_pw])
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


# ── Sent / Outbound Stats ────────────────────────────────────────────────────


@router.get("/mailbox/stats/sent/bulk")
async def bulk_sent_stats(
    _identity: str = Depends(verify_service_identity),
):
    """
    Return cached bulk sent stats for all senders.
    If stale, triggers background refresh and returns cached data.
    """
    return await get_sent_stats_cached()


@router.post("/mailbox/stats/sent/refresh")
async def trigger_sent_refresh(
    _identity: str = Depends(verify_service_identity),
):
    """Force-refresh sent stats now (blocking)."""
    stats, error = await refresh_sent_stats()
    return {"ok": error is None, "count": len(stats), "error": error}


@router.get("/mailbox/{email_addr}/sent")
async def mailbox_sent_detail(
    email_addr: str,
    limit: int = 50,
    _identity: str = Depends(verify_service_identity),
):
    """Get recent sent message detail for a mailbox."""
    return await get_sent_detail(email_addr, limit=limit)
