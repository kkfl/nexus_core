"""
Adapter factory -- selects the correct ServerProviderAdapter for a host.
Credentials fetched from secrets-agent at runtime by alias.
Never cached beyond request lifecycle. Never logged.
"""

from __future__ import annotations

import structlog

from apps.server_agent.adapters.base import ServerProviderAdapter
from apps.server_agent.adapters.vultr import VultrAdapter
from apps.server_agent.adapters.proxmox import ProxmoxAdapter
from apps.server_agent.config import get_settings

logger = structlog.get_logger(__name__)


async def get_adapter(
    provider: str,
    host_config: dict,
    secret_value: str,
    correlation_id: str | None = None,
) -> ServerProviderAdapter:
    """
    Build and return the correct adapter for the given provider.
    secret_value is already fetched from vault -- used immediately, never stored.

    Args:
        provider: "vultr" or "proxmox"
        host_config: provider-specific config from server_hosts.config
        secret_value: credential value from vault (API key or token string)
        correlation_id: for logging
    """
    settings = get_settings()

    if provider == "vultr":
        return VultrAdapter(
            api_key=secret_value,
            base_url=settings.vultr_api_base,
        )

    elif provider == "proxmox":
        return ProxmoxAdapter(
            base_url=host_config.get("base_url", "https://localhost:8006"),
            api_token=secret_value,
            node=host_config.get("node", "pve"),
            verify_ssl=settings.proxmox_verify_ssl,
        )

    else:
        raise ValueError(f"Unknown server provider: '{provider}'. Supported: vultr, proxmox")
