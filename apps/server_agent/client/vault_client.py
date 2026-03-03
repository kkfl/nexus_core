"""Vault client for the Server Agent -- fetches secrets from secrets-agent."""

from __future__ import annotations

import httpx
import structlog

from apps.server_agent.config import get_settings

logger = structlog.get_logger(__name__)


class ServerVaultClient:
    """Thin wrapper around secrets-agent HTTP API (2-step: list -> read)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.vault_base_url
        self._service_id = settings.vault_service_id
        self._agent_key = settings.vault_agent_key

    def _headers(self, correlation_id: str | None = None) -> dict:
        h = {
            "X-Service-ID": self._service_id,
            "X-Agent-Key": self._agent_key,
        }
        if correlation_id:
            h["X-Correlation-ID"] = correlation_id
        return h

    async def get_secret(
        self,
        alias: str,
        tenant_id: str,
        env: str,
        reason: str = "server_adapter_init",
        correlation_id: str | None = None,
    ) -> str:
        """
        Fetch a secret value from the vault by alias.
        Uses the 2-step pattern: list -> find by alias -> read decrypted value.
        Never cache the result.
        """
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10) as client:
            # Step 1: List secrets for tenant/env and find matching alias
            list_resp = await client.get(
                "/v1/secrets",
                params={"tenant_id": tenant_id, "env": env},
                headers=self._headers(correlation_id),
            )
            if list_resp.status_code != 200:
                logger.error(
                    "vault_list_failed",
                    alias=alias,
                    status=list_resp.status_code,
                    correlation_id=correlation_id,
                )
                raise RuntimeError(
                    f"Vault list failed for alias={alias}: status={list_resp.status_code}"
                )

            items = list_resp.json()
            matched = next((s for s in items if s.get("alias") == alias), None)
            if not matched:
                raise RuntimeError(
                    f"Secret alias '{alias}' not found for tenant={tenant_id} env={env}"
                )

            secret_id = matched["id"]

            # Step 2: Read (decrypt) the secret value
            read_resp = await client.post(
                f"/v1/secrets/{secret_id}/read",
                json={"reason": reason},
                headers=self._headers(correlation_id),
            )
            if read_resp.status_code != 200:
                logger.error(
                    "vault_read_failed",
                    alias=alias,
                    status=read_resp.status_code,
                    correlation_id=correlation_id,
                )
                raise RuntimeError(
                    f"Vault read failed for alias={alias}: status={read_resp.status_code}"
                )

            return read_resp.json().get("value", "")
