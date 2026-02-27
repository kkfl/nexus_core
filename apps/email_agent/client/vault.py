"""
Vault client for email_agent — resolves secrets from secrets-agent.
"""

from __future__ import annotations

import httpx
import structlog

from apps.email_agent.config import config

logger = structlog.get_logger(__name__)


async def get_secret(alias: str, tenant_id: str = "nexus", env: str = "prod") -> str:
    """Resolve a secret value by alias. Never logs the value."""
    headers = {
        "X-Service-ID": config.vault_service_id,
        "X-Agent-Key": config.vault_agent_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=config.vault_base_url, timeout=5.0) as c:
        # List secrets to find ID
        resp = await c.get(
            "/v1/secrets",
            params={"tenant_id": tenant_id, "env": env},
            headers=headers,
        )
        resp.raise_for_status()
        matched = next((s for s in resp.json() if s["alias"] == alias), None)
        if not matched:
            raise RuntimeError(f"Secret alias '{alias}' not found in vault")
        # Read value
        read_resp = await c.post(
            f"/v1/secrets/{matched['id']}/read",
            json={"reason": f"email_agent:{alias}"},
            headers=headers,
        )
        read_resp.raise_for_status()
        return read_resp.json()["value"]
