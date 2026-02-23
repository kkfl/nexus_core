"""
VaultClient — the client library that other agents embed to request secrets.

Usage example (PBX Agent):

    from apps.secrets_agent.client.vault_client import VaultClient

    client = VaultClient(
        base_url=os.environ["VAULT_BASE_URL"],    # e.g. http://secrets-agent:8007
        service_id=os.environ["VAULT_SERVICE_ID"],  # e.g. "pbx-agent"
        api_key=os.environ["VAULT_AGENT_KEY"],
    )

    # At runtime, never at module load time:
    sip_password = await client.get_secret("pbx.sip.trunk.password", tenant_id="nexus", env="prod")
    # sip_password is a str — use immediately, never cache, never log.

Design rules:
- Never logs the returned value (uses SafeValue internally during transport).
- Honors correlation_id for distributed tracing.
- Raises VaultAccessDenied (403), VaultNotFound (404), or VaultError on failure.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from apps.secrets_agent.crypto.redaction import SafeValue

logger = logging.getLogger(__name__)


class VaultError(Exception):
    pass


class VaultAccessDenied(VaultError):
    pass


class VaultNotFound(VaultError):
    pass


class VaultClient:
    def __init__(
        self,
        base_url: str,
        service_id: str,
        api_key: str,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_id = service_id
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self, correlation_id: Optional[str] = None) -> dict[str, str]:
        h = {
            "X-Service-ID": self._service_id,
            "X-Agent-Key": self._api_key,
            "Content-Type": "application/json",
        }
        if correlation_id:
            h["X-Correlation-ID"] = correlation_id
            h["X-Request-ID"] = correlation_id
        return h

    async def get_secret(
        self,
        alias: str,
        tenant_id: str,
        env: str,
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Retrieve a plaintext secret value by alias.
        The value is NEVER logged — only the alias is.

        Raises:
            VaultNotFound: secret does not exist.
            VaultAccessDenied: policy denied access.
            VaultError: any other failure.
        """
        logger.info(
            "vault_get_secret_request",
            alias=alias,
            tenant_id=tenant_id,
            env=env,
            correlation_id=correlation_id,
            # value is intentionally not logged anywhere here
        )
        # Step 1: find secret ID by alias
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            list_resp = await client.get(
                "/v1/secrets",
                params={"tenant_id": tenant_id, "env": env},
                headers=self._headers(correlation_id),
            )
            if list_resp.status_code == 403:
                raise VaultAccessDenied(f"Access denied listing secrets for alias '{alias}'.")
            if list_resp.status_code != 200:
                raise VaultError(f"Vault list failed: {list_resp.status_code}")

            items = list_resp.json()
            matched = next((s for s in items if s["alias"] == alias), None)
            if not matched:
                raise VaultNotFound(f"Secret alias '{alias}' not found for tenant={tenant_id} env={env}.")

            secret_id = matched["id"]

            # Step 2: read (decrypt) the secret value
            read_resp = await client.post(
                f"/v1/secrets/{secret_id}/read",
                json={"reason": reason or "runtime_fetch"},
                headers=self._headers(correlation_id),
            )
            if read_resp.status_code == 403:
                raise VaultAccessDenied(f"Access denied reading secret alias '{alias}'.")
            if read_resp.status_code == 404:
                raise VaultNotFound(f"Secret '{alias}' not found during read.")
            if read_resp.status_code != 200:
                raise VaultError(f"Vault read failed: {read_resp.status_code}")

            data = read_resp.json()
            # Wrap in SafeValue to prevent accidental logging by caller code
            safe = SafeValue(data["value"])
            logger.info(
                "vault_get_secret_success",
                alias=alias,
                tenant_id=tenant_id,
                env=env,
                value=safe,   # SafeValue.__str__ returns [REDACTED]
            )
            # Return the raw string — caller uses it immediately
            return safe.unsafe_value


# ---------------------------------------------------------------------------
# Convenience factory from environment variables
# ---------------------------------------------------------------------------

def vault_client_from_env() -> VaultClient:
    """
    Create a VaultClient from standard environment variables:
      VAULT_BASE_URL      = http://secrets-agent:8007
      VAULT_SERVICE_ID    = pbx-agent
      VAULT_AGENT_KEY     = <api key>
    """
    return VaultClient(
        base_url=os.environ["VAULT_BASE_URL"],
        service_id=os.environ["VAULT_SERVICE_ID"],
        api_key=os.environ["VAULT_AGENT_KEY"],
    )
