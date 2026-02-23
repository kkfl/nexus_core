"""
Adapter factory — selects the correct DnsProviderAdapter for a zone.

Credentials are fetched from secrets_agent at runtime by alias.
Never cached beyond the request lifecycle. Never logged.
"""

from __future__ import annotations

import structlog

from apps.dns_agent.adapters.base import DnsProviderAdapter
from apps.dns_agent.adapters.cloudflare import CloudflareAdapter
from apps.dns_agent.adapters.dnsmadeeasy import DNSMadeEasyAdapter
from apps.dns_agent.client.vault_client import DnsVaultClient

logger = structlog.get_logger(__name__)


async def get_adapter(
    provider: str,
    tenant_id: str,
    env: str,
    vault: DnsVaultClient,
    correlation_id: str | None = None,
) -> DnsProviderAdapter:
    """
    Build and return the correct adapter for the given provider.
    Credentials are fetched from the vault at call time — never cached.

    Raises VaultNotFound, VaultAccessDenied, or RuntimeError.
    """
    if provider == "cloudflare":
        token = await vault.get_secret(
            alias="dns.cloudflare.api_token",
            tenant_id=tenant_id,
            env=env,
            reason="dns_adapter_init",
            correlation_id=correlation_id,
        )
        # Token used immediately — not stored in a named variable that could leak to logs
        return CloudflareAdapter(api_token=token)

    elif provider == "dnsmadeeasy":
        api_key = await vault.get_secret(
            alias="dns.dnsmadeeasy.api_key",
            tenant_id=tenant_id,
            env=env,
            reason="dns_adapter_init",
            correlation_id=correlation_id,
        )
        secret_key = await vault.get_secret(
            alias="dns.dnsmadeeasy.secret_key",
            tenant_id=tenant_id,
            env=env,
            reason="dns_adapter_init",
            correlation_id=correlation_id,
        )
        return DNSMadeEasyAdapter(api_key=api_key, secret_key=secret_key)

    else:
        raise ValueError(f"Unknown DNS provider: '{provider}'. Supported: cloudflare, dnsmadeeasy")
