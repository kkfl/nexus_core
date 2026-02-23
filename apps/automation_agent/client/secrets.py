import httpx
import structlog

from apps.automation_agent.client.registry import resolve_agent
from apps.automation_agent.config import config

logger = structlog.get_logger(__name__)


async def fetch_secret(
    secret_alias: str, tenant_id: str, env: str, correlation_id: str
) -> dict | None:
    """
    Retrieves a secret from the secrets-agent.
    Dynamically resolves secrets-agent URL.
    """
    try:
        agent = await resolve_agent("secrets-agent", tenant_id, env)
    except RuntimeError as ex:
        logger.error("secrets_agent_resolution_failed", error=str(ex))
        return None

    headers = {
        "X-Service-ID": "automation-agent",
        "X-Agent-Key": config.automation_agent_keys.get(
            "automation-agent", "internal-automation-key"
        ),  # Usually vault gives each agent their own key
        "X-Correlation-ID": correlation_id,
    }

    # Actually wait we need to use the token designed for automation-agent to call vault.
    # Usually it's in the env as something like AUTOMATION_VAULT_AGENT_KEY.
    # Let's use a generic internal key concept if missing
    vault_key = config.automation_vault_agent_key
    headers["X-Agent-Key"] = vault_key

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # First lookup the secret ID by alias
            lookup_url = f"{agent.base_url}/v1/secrets?tenant_id={tenant_id}&env={env}"
            lookup_resp = await client.get(lookup_url, headers=headers)
            lookup_resp.raise_for_status()

            secrets_list = lookup_resp.json()
            secret_id = None
            for s in secrets_list:
                if s["alias"] == secret_alias:
                    secret_id = s["id"]
                    break

            if not secret_id:
                logger.warning("secret_alias_not_found", alias=secret_alias)
                return None

            # Now read the decrypted value
            read_url = f"{agent.base_url}/v1/secrets/{secret_id}/read"
            read_resp = await client.post(
                read_url, headers=headers, json={"reason": "automation agent execution"}
            )
            read_resp.raise_for_status()
            return read_resp.json()["value"]
    except Exception as e:
        logger.error("secrets_fetch_failed", alias=secret_alias, error=str(e))
        return None
