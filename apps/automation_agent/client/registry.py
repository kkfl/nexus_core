import structlog

from apps.automation_agent.config import config
from packages.shared.client.agent_registry import AgentRegistryClient, ResolvableAgent

logger = structlog.get_logger(__name__)

# Cache registry client instance
_client = None


def get_registry_client() -> AgentRegistryClient:
    global _client
    if _client is None:
        _client = AgentRegistryClient(
            registry_base_url=config.registry_base_url,
            agent_key=config.nexus_registry_agent_key,
            service_id="nexus",
        )
    return _client


async def resolve_agent(agent_name: str, tenant_id: str, env: str) -> ResolvableAgent:
    """Helper to resolve an agent and throw a clear error if missing."""
    client = get_registry_client()
    agent = await client.resolve_agent(agent_name, tenant_id, env)
    if not agent:
        raise RuntimeError(
            f"Could not resolve agent '{agent_name}' for tenant '{tenant_id}' in env '{env}'"
        )
    return agent
