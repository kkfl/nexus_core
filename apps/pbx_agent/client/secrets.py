"""
Secrets-agent client for pbx_agent.
Fetches AMI credentials + other PBX secrets at runtime by alias.
NEVER logs the returned secret value.
"""

import httpx
import structlog

from apps.pbx_agent.config import config

logger = structlog.get_logger(__name__)


class SecretsError(Exception):
    pass


async def fetch_secret(
    alias: str,
    tenant_id: str,
    env: str,
    reason: str = "pbx_operation",
    correlation_id: str = "",
) -> str:
    """
    Retrieve a secret value from secrets-agent by alias.
    Uses the read-by-alias endpoint for direct alias lookup + decrypt.
    Raises SecretsError on failure.
    Never returns or logs the secret in the error path.
    """
    url = f"{config.vault_base_url}/v1/secrets/read-by-alias"
    headers = {
        "X-Service-ID": config.vault_service_id,
        "X-Agent-Key": config.pbx_vault_agent_key,
        "X-Correlation-ID": correlation_id,
    }
    body = {"alias": alias, "tenant_id": tenant_id, "env": env, "reason": reason}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code == 404:
            raise SecretsError(f"Secret alias '{alias}' not found in secrets-agent")
        if r.status_code == 403:
            raise SecretsError(f"pbx-agent not authorized to read alias '{alias}'")
        r.raise_for_status()
        value = r.json().get("value")
        if not value:
            raise SecretsError(f"secrets-agent returned empty value for alias '{alias}'")
        return value
    except SecretsError:
        raise
    except Exception as e:
        raise SecretsError(f"secrets-agent unreachable: {type(e).__name__}") from None


async def store_secret(
    alias: str,
    value: str,
    tenant_id: str,
    env: str,
    description: str = "",
    correlation_id: str = "",
) -> str:
    """
    Create or update a secret in secrets-agent.
    If the alias already exists (409), rotates the value.
    Returns the secret ID on success.
    Raises SecretsError on failure.
    """
    url = f"{config.vault_base_url}/v1/secrets"
    headers = {
        "X-Service-ID": config.vault_service_id,
        "X-Agent-Key": config.pbx_vault_agent_key,
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }
    body = {
        "alias": alias,
        "tenant_id": tenant_id,
        "env": env,
        "value": value,
        "description": description,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=body)

        if r.status_code == 409:
            # Secret alias already exists — rotate to the new value
            logger.info("secret_alias_exists_rotating", alias=alias)
            return await _rotate_existing(alias, value, tenant_id, env, headers)
        if r.status_code == 403:
            raise SecretsError(f"pbx-agent not authorized to write alias '{alias}'")
        r.raise_for_status()
        return r.json().get("id", "unknown")
    except SecretsError:
        raise
    except Exception as e:
        raise SecretsError(
            f"secrets-agent write failed: {type(e).__name__}: {str(e)[:200]}"
        ) from None


async def _rotate_existing(
    alias: str,
    new_value: str,
    tenant_id: str,
    env: str,
    headers: dict,
) -> str:
    """Read existing secret by alias and rotate to new value."""
    read_url = f"{config.vault_base_url}/v1/secrets/read-by-alias"
    read_body = {"alias": alias, "tenant_id": tenant_id, "env": env, "reason": "rotate_on_edit"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(read_url, headers=headers, json=read_body)
            r.raise_for_status()
            secret_id = r.json()["id"]

            rotate_url = f"{config.vault_base_url}/v1/secrets/{secret_id}/rotate"
            r2 = await client.post(rotate_url, headers=headers, json={"new_value": new_value})
            r2.raise_for_status()
            logger.info("secret_rotated_on_edit", alias=alias, secret_id=secret_id)
            return secret_id
    except Exception as e:
        raise SecretsError(
            f"rotate-on-edit failed for '{alias}': {type(e).__name__}: {str(e)[:200]}"
        ) from None


async def delete_secret_by_alias(
    alias: str,
    tenant_id: str,
    env: str,
    correlation_id: str = "",
) -> bool:
    """
    Delete a secret from secrets-agent by alias.
    Returns True if deleted, False if not found.
    """
    headers = {
        "X-Service-ID": config.vault_service_id,
        "X-Agent-Key": config.pbx_vault_agent_key,
        "X-Correlation-ID": correlation_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Look up the secret ID by alias
            r = await client.post(
                f"{config.vault_base_url}/v1/secrets/read-by-alias",
                headers=headers,
                json={
                    "alias": alias,
                    "tenant_id": tenant_id,
                    "env": env,
                    "reason": "delete_cleanup",
                },
            )
            if r.status_code == 404:
                return False  # Secret doesn't exist — nothing to delete
            r.raise_for_status()
            secret_id = r.json().get("id")
            if not secret_id:
                return False

            # Delete the secret
            dr = await client.delete(
                f"{config.vault_base_url}/v1/secrets/{secret_id}?reason=pbx_target_deleted",
                headers=headers,
            )
            return dr.status_code in (200, 204)
    except Exception as e:
        logger.warning("secret_delete_failed", alias=alias, error=str(e)[:100])
        return False
