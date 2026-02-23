import structlog
from typing import Optional

from apps.storage_agent.config import get_settings

logger = structlog.get_logger(__name__)

async def get_secret(alias: str, tenant_id: str = "nexus", env: str = "prod", correlation_id: Optional[str] = None) -> Optional[str]:
    """Retrieve an individual secret from the Secrets Agent securely."""
    import httpx
    settings = get_settings()
    
    headers = {
        "X-Service-ID": settings.vault_service_id,
        "X-Agent-Key": settings.vault_agent_key,
    }
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
        
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            logger.info("fetching_vault_secrets_list", url=f"{settings.vault_base_url}/v1/secrets", params={"tenant_id": tenant_id, "env": env})
            resp = await client.get(
                f"{settings.vault_base_url}/v1/secrets",
                params={"tenant_id": tenant_id, "env": env}, 
                headers=headers
            )
            
            logger.info("vault_list_response", status=resp.status_code, body=resp.text)
            if resp.status_code == 200:
                secrets = resp.json()
                for s in secrets:
                    if s.get("alias") == alias:
                        s_id = s.get("id")
                        logger.info("reading_vault_secret", s_id=s_id)
                        read_resp = await client.post(
                            f"{settings.vault_base_url}/v1/secrets/{s_id}/read",
                            json={"reason": "storage-agent outbound check"},
                            headers=headers
                        )
                        logger.info("vault_read_response", status=read_resp.status_code)
                        if read_resp.status_code == 200:
                            data = read_resp.json()
                            return data.get("value")
            
            # Silent logging - only correlation id
            logger.warning(
                "secret_not_found_or_access_denied",
                alias=alias,
                tenant_id=tenant_id,
                env=env,
                correlation_id=correlation_id
            )
            return None
            
    except Exception as e:
        logger.error(
            "vault_connection_failure",
            error=str(e),
            alias=alias,
            correlation_id=correlation_id
        )
        return None
