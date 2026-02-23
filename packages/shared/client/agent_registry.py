"""
Agent Registry Client Library for Nexus
Used by nexus_api (or other platform components) to dynamically resolve agent endpoints and auth.
"""
import os
from typing import Dict, Optional, Any, List

import httpx
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)


class ResolvableAgent(BaseModel):
    agent_id: str
    name: str # e.g. dns-agent
    base_url: str
    auth_scheme: str
    auth_secret_alias: Optional[str] = None
    health_endpoint: Optional[str] = "/healthz"
    capabilities_endpoint: Optional[str] = None


class AgentRegistryClient:
    def __init__(self, registry_base_url: str, agent_key: str, service_id: str = "nexus", timeout: int = 5):
        self.registry_base_url = registry_base_url.rstrip("/")
        self.headers = {
            "X-Service-ID": service_id,
            "X-Agent-Key": agent_key,
            "Content-Type": "application/json"
        }
        self.timeout = timeout

    async def list_agents(self) -> List[Dict[str, Any]]:
        """Returns the list of all active agents"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.registry_base_url}/v1/agents", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def resolve_agent(self, agent_name: str, tenant_id: Optional[str], env: str) -> Optional[ResolvableAgent]:
        """
        Dynamically locates the correct deployment for an agent by name, tenant, and environment.
        Falls back to a tenant_id=None global deployment if a tenant-specific one isn't found.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 1. Look up agent by name
            agent_resp = await client.get(f"{self.registry_base_url}/v1/agents/{agent_name}", headers=self.headers)
            if agent_resp.status_code == 404:
                return None
            agent_resp.raise_for_status()
            agent_data = agent_resp.json()
            agent_id = agent_data["id"]

            if agent_data.get("status") == "disabled":
                logger.warning("registry_agent_disabled", agent_name=agent_name)
                return None

            # 2. Look up deployments for this environment and agent_id
            query = f"?env={env}&agent_id={agent_id}"
                
            deps_resp = await client.get(f"{self.registry_base_url}/v1/deployments{query}", headers=self.headers)
            deps_resp.raise_for_status()
            deps = deps_resp.json()

            # Find matching deployment
            # If we asked for tenant_id, prioritize exact match. Otherwise take the global one (tenant_id=None)
            target_dep = None
            for d in deps:
                if d["agent_id"] == agent_id:
                    if target_dep is None:
                        target_dep = d
                    else:
                        # Prioritize exact tenant match over global fallback
                        if d["tenant_id"] == tenant_id:
                            target_dep = d

            if not target_dep:
                return None

            return ResolvableAgent(
                agent_id=agent_id,
                name=agent_name,
                base_url=target_dep["base_url"],
                auth_scheme=target_dep.get("auth_scheme", "headers"),
                auth_secret_alias=target_dep.get("auth_secret_alias"),
                health_endpoint=target_dep.get("health_endpoint"),
                capabilities_endpoint=target_dep.get("capabilities_endpoint"),
            )


# Singleton instance helper
def get_registry_client() -> AgentRegistryClient:
    url = os.environ.get("REGISTRY_BASE_URL", "http://agent-registry:8012")
    key = os.environ.get("NEXUS_REGISTRY_AGENT_KEY", "nexus-registry-key")
    return AgentRegistryClient(registry_base_url=url, agent_key=key)
