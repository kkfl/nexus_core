"""
Secrets agent client for fetching outbound credentials
"""
import httpx
import structlog
from typing import Optional
from apps.monitoring_agent.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

async def get_secret(alias: str, tenant_id: str, env: str, correlation_id: str) -> Optional[str]:
    headers = {
        "X-Service-ID": settings.vault_service_id,
        "X-Agent-Key": settings.vault_agent_key,
        "X-Correlation-ID": correlation_id
    }
    
    # We query the vault for the given alias.
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.vault_base_url}/v1/secrets",
                params={"tenant_id": tenant_id, "env": env},
                headers=headers
            )
            if resp.status_code == 200:
                secrets = resp.json()
                for s in secrets:
                    if s.get("alias") == alias:
                        # Found it. Now read it to get the actual value
                        s_id = s.get("id")
                        read_resp = await client.post(
                            f"{settings.vault_base_url}/v1/secrets/{s_id}/read",
                            json={"reason": "monitoring-agent outbound check"},
                            headers=headers
                        )
                        if read_resp.status_code == 200:
                            data = read_resp.json()
                            return data.get("value")
                            
            logger.warning("secret_not_found_or_access_denied", alias=alias, tenant_id=tenant_id, env=env)
            return None
    except Exception as e:
        logger.error("vault_fetch_failed", error=str(e), alias=alias)
        return None
