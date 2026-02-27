"""
email_agent — health endpoint.
Runs all connectivity checks concurrently with hard timeouts.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from apps.email_agent.schemas import HealthStatus

router = APIRouter(prefix="/email", tags=["health"])


async def _safe_check(coro, label):
    """Run a check with a hard 10s timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=10)
    except asyncio.TimeoutError:
        return False, f"{label} timed out"
    except Exception as e:
        return False, str(e)[:200]


@router.get("/health", response_model=HealthStatus)
async def health():
    """Check SMTP + IMAP + SSH bridge connectivity (concurrent, 10s timeout each)."""
    from apps.email_agent.client.ssh_bridge import check_ssh_connectivity
    from apps.email_agent.services.imap import check_imap_connectivity
    from apps.email_agent.services.smtp import check_smtp_connectivity

    smtp_result, imap_result, ssh_result = await asyncio.gather(
        _safe_check(check_smtp_connectivity(), "SMTP"),
        _safe_check(check_imap_connectivity(), "IMAP"),
        _safe_check(check_ssh_connectivity(), "SSH"),
    )

    smtp_ok, smtp_detail = smtp_result
    imap_ok, imap_detail = imap_result
    ssh_ok, ssh_detail = ssh_result

    return HealthStatus(
        smtp="ok" if smtp_ok else "error",
        imap="ok" if imap_ok else "error",
        ssh_bridge="ok" if ssh_ok else "error",
        smtp_detail=smtp_detail if not smtp_ok else None,
        imap_detail=imap_detail if not imap_ok else None,
        ssh_detail=ssh_detail if not ssh_ok else None,
    )
