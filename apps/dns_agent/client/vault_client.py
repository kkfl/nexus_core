"""
DnsVaultClient — thin wrapper around the shared VaultClient for the dns_agent.

Imports the VaultClient from secrets_agent package for reuse.
Provides a convenience factory from DNS_AGENT-specific env vars.
"""
from __future__ import annotations

import os

# Re-use the VaultClient directly from the secrets_agent package
from apps.secrets_agent.client.vault_client import (
    VaultClient,
    VaultAccessDenied,
    VaultError,
    VaultNotFound,
)

__all__ = ["DnsVaultClient", "VaultAccessDenied", "VaultError", "VaultNotFound"]


class DnsVaultClient(VaultClient):
    """
    VaultClient specialized for the dns_agent.
    Same API as VaultClient — secret values never logged.
    """
    pass


def dns_vault_client_from_env() -> DnsVaultClient:
    """
    Create a DnsVaultClient from environment variables:
      VAULT_BASE_URL   = http://secrets-agent:8007
      VAULT_SERVICE_ID = dns-agent
      VAULT_AGENT_KEY  = <api key matching DNS_AGENT entry in vault>
    """
    return DnsVaultClient(
        base_url=os.environ.get("VAULT_BASE_URL", "http://secrets-agent:8007"),
        service_id=os.environ.get("VAULT_SERVICE_ID", "dns-agent"),
        api_key=os.environ["VAULT_AGENT_KEY"],
    )
