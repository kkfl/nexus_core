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
    Raises SecretsError on failure.
    Never returns or logs the secret in the error path.
    """
    url = f"{config.vault_base_url}/v1/secrets/{alias}"
    headers = {
        "X-Service-ID": config.vault_service_id,
        "X-Agent-Key": config.pbx_vault_agent_key,
        "X-Correlation-ID": correlation_id,
    }
    params = {"tenant_id": tenant_id, "env": env, "reason": reason}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers=headers, params=params)
        if r.status_code == 404:
            raise SecretsError(f"Secret alias '{alias}' not found in secrets-agent")
        if r.status_code == 403:
            raise SecretsError(f"pbx-agent not authorized to access alias '{alias}'")
        r.raise_for_status()
        value = r.json().get("value") or r.json().get("secret")
        if not value:
            raise SecretsError(f"secrets-agent returned empty value for alias '{alias}'")
        return value
    except SecretsError:
        raise
    except Exception as e:
        # Never include URL params (could contain creds if misconfigured)
        raise SecretsError(f"secrets-agent unreachable: {type(e).__name__}") from None
