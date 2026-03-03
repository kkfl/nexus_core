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
from sqlalchemy.ext.asyncio import AsyncSession

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
from packages.shared.db import get_db

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Email credential endpoints
# ---------------------------------------------------------------------------


async def _resolve_email_agent() -> tuple[str, str]:
    """Resolve email_agent base_url and auth key."""
    registry = get_registry_client()
    agent = await registry.resolve_agent("email-agent", tenant_id=None, env="prod")
    base_url = (
        agent.base_url if agent else os.environ.get("EMAIL_AGENT_URL", "http://email-agent:8014")
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


# ---------------------------------------------------------------------------
# Dashboard Aggregation
# ---------------------------------------------------------------------------


@router.get("/dashboard/summary")
async def dashboard_summary(
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import httpx

    from packages.shared.client.agent_registry import get_registry_client

    registry = get_registry_client()

    # 1. Fetch agents
    from sqlalchemy import func, select

    from packages.shared.models.core import BusEvent

    recent_activity = []
    total_agents = 0
    active_agents = 0
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{registry.registry_base_url}/v1/agents", headers=registry.headers
            )
            if resp.status_code == 200:
                agents_list = resp.json()
                total_agents = len(agents_list)
                for a in agents_list:
                    status = a.get("status", "unknown")
                    name = a.get("name")
                    if status == "active":
                        active_agents += 1

                    # Find latest event produced by this agent
                    stmt = select(func.max(BusEvent.occurred_at)).where(
                        BusEvent.produced_by == name
                    )
                    result = await db.execute(stmt)
                    latest_timestamp = result.scalar()

                    recent_activity.append(
                        {
                            "name": name,
                            "status": status,
                            "last_seen_at": latest_timestamp if latest_timestamp else None,
                        }
                    )
        # Sort activity by most recently seen
        recent_activity.sort(
            key=lambda x: str(x["last_seen_at"]) if x["last_seen_at"] else "", reverse=True
        )
    except Exception as e:
        logger.warning("dashboard_fetch_agents_failed", error=str(e))

    # 2. Fetch servers
    total_servers = 0
    active_servers = 0
    try:
        server_agent = await registry.resolve_agent("server-agent", None, "prod")
        server_base = (
            server_agent.base_url
            if server_agent
            else os.environ.get("SERVER_AGENT_URL", "http://server-agent:8002")
        )
        # server_agent gets the current identity if proxying via bearer token, but for internal reads we can just GET
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{server_base}/v1/servers")
            if resp.status_code == 200:
                servers_data = resp.json()
                total_servers = len(servers_data)
                active_servers = sum(1 for s in servers_data if s.get("power_status") == "running")
    except Exception as e:
        logger.warning("dashboard_fetch_servers_failed", error=str(e))

    # 3. Fetch mailboxes
    total_mailboxes = 0
    inbound_unread = 0
    try:
        email_base, email_key = await _resolve_email_agent()
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                f"{email_base}/email/admin/mailbox/stats/bulk",
                headers={"X-Service-ID": "nexus", "X-Agent-Key": email_key},
            )
            if resp.status_code == 200:
                stats_res = resp.json()
                stats = stats_res.get("stats", [])
                total_mailboxes = len(stats)
                inbound_unread = sum(s.get("unread_count", 0) for s in stats)
    except Exception as e:
        logger.warning("dashboard_fetch_email_failed", error=str(e))

    # 4. Fetch recent transactions (system-wide event bus)
    recent_transactions = []
    try:
        stmt = select(BusEvent).order_by(BusEvent.occurred_at.desc()).limit(15)
        result = await db.execute(stmt)
        events = result.scalars().all()
        for ev in events:
            recent_transactions.append(
                {
                    "timestamp": ev.occurred_at,
                    "source": ev.produced_by,
                    "action": ev.event_type,
                    "severity": ev.severity,
                }
            )
    except Exception as e:
        logger.warning("dashboard_fetch_transactions_failed", error=str(e))

    return {
        "metrics": {
            "agents": {"total": total_agents, "active": active_agents},
            "servers": {"total": total_servers, "active": active_servers},
            "mail": {"total_mailboxes": total_mailboxes, "inbound_unread": inbound_unread},
        },
        "recent_activity": recent_activity,
        "recent_transactions": recent_transactions,
    }
