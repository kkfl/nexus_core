"""
Auto-seed server_hosts from vault credentials at startup.

Discovers vault secrets matching ``server.*`` aliases and idempotently
creates corresponding ServerHost records so the sync worker has hosts
to iterate over.

This ensures credentials stored in the vault are automatically usable
without manual host registration via API.
"""

from __future__ import annotations

import uuid

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.config import get_settings
from apps.server_agent.models import ServerHost

logger = structlog.get_logger(__name__)

# Map vault alias prefixes to provider + label templates
_PROVIDER_MAP: dict[str, dict] = {
    "server.vultr.": {
        "provider": "vultr",
        "label_prefix": "Vultr",
    },
    "server.proxmox.": {
        "provider": "proxmox",
        "label_prefix": "Proxmox",
    },
}


async def seed_hosts_from_vault(db: AsyncSession) -> int:
    """
    Query secrets-agent for ``server.*`` aliases and create matching hosts.

    Returns the number of newly created host records.
    """
    settings = get_settings()
    base_url = settings.vault_base_url
    service_id = settings.vault_service_id
    agent_key = settings.vault_agent_key

    if not agent_key:
        logger.warning("seed_hosts_skipped", reason="no vault_agent_key configured")
        return 0

    headers = {"X-Service-ID": service_id, "X-Agent-Key": agent_key}

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            resp = await client.get(
                "/v1/secrets",
                params={"tenant_id": "nexus", "env": "prod"},
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(
                    "seed_hosts_vault_error",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
                return 0
            vault_secrets = resp.json()
    except Exception as exc:
        logger.warning("seed_hosts_vault_unreachable", error=str(exc))
        return 0

    created = 0
    for secret in vault_secrets:
        alias = secret.get("alias", "")
        if not secret.get("is_active", False):
            continue

        for prefix, info in _PROVIDER_MAP.items():
            if not alias.startswith(prefix):
                continue

            provider = info["provider"]
            label = f"{info['label_prefix']} Production"

            # Check if host already exists for this alias
            existing = await db.execute(select(ServerHost).where(ServerHost.secret_alias == alias))
            if existing.scalars().first():
                logger.debug("seed_hosts_exists", alias=alias, provider=provider)
                break

            # Build provider-specific config
            config: dict = {}
            if provider == "proxmox":
                config["base_url"] = settings.proxmox_base_url
                config["node"] = settings.proxmox_node

            host = ServerHost(
                id=str(uuid.uuid4()),
                tenant_id="nexus",
                env="prod",
                provider=provider,
                label=label,
                config=config,
                secret_alias=alias,
                is_active=True,
            )
            db.add(host)
            created += 1
            logger.info(
                "seed_hosts_created",
                alias=alias,
                provider=provider,
                label=label,
                host_id=host.id,
            )
            break

    if created:
        await db.commit()

    logger.info("seed_hosts_complete", created=created, total_vault_secrets=len(vault_secrets))
    return created
