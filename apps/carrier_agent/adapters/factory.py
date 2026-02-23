"""
Carrier adapter factory.
Credentials fetched from secrets_agent at runtime. Never cached.
"""
from __future__ import annotations

from typing import Optional

import structlog

from apps.carrier_agent.adapters.base import CarrierProviderAdapter
from apps.carrier_agent.adapters.mock import MockCarrierAdapter
from apps.carrier_agent.adapters.twilio import TwilioAdapter
from apps.secrets_agent.client.vault_client import VaultClient, VaultError

logger = structlog.get_logger(__name__)


async def get_adapter(provider: str, target_id: str,
                      vault: VaultClient,
                      tenant_id: str = "nexus",
                      env: str = "prod",
                      correlation_id: Optional[str] = None) -> CarrierProviderAdapter:
    """
    Build the correct adapter for the given provider.
    Credentials fetched from vault at call time — never cached, never logged.
    """
    if provider == "mock":
        return MockCarrierAdapter()

    elif provider == "twilio":
        account_sid = await vault.get_secret(
            alias=f"carrier.{target_id}.account_sid",
            tenant_id=tenant_id,
            env=env,
            reason="carrier_adapter_init",
            correlation_id=correlation_id,
        )
        auth_token = await vault.get_secret(
            alias=f"carrier.{target_id}.auth_token",
            tenant_id=tenant_id,
            env=env,
            reason="carrier_adapter_init",
            correlation_id=correlation_id,
        )
        return TwilioAdapter(account_sid=account_sid, auth_token=auth_token)

    else:
        raise ValueError(f"Unknown carrier provider: '{provider}'. Supported: twilio, mock")
