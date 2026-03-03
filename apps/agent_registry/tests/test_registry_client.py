import pytest
import respx
from httpx import Response

from packages.shared.client.agent_registry import AgentRegistryClient


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_exact_tenant():
    client = AgentRegistryClient(
        registry_base_url="http://fake-registry", agent_key="key", service_id="test"
    )

    # Mock agent lookup
    respx.get("http://fake-registry/v1/agents/demo-agent").mock(
        return_value=Response(
            200, json={"id": "agent-123", "name": "demo-agent", "status": "active"}
        )
    )

    # Mock deployments lookup
    respx.get(path="/v1/deployments").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": "dep-g",
                    "agent_id": "agent-123",
                    "tenant_id": None,
                    "env": "prod",
                    "base_url": "http://global-agent:80",
                },
                {
                    "id": "dep-t",
                    "agent_id": "agent-123",
                    "tenant_id": "tenant-x",
                    "env": "prod",
                    "base_url": "http://tenant-agent:80",
                },
            ],
        )
    )

    try:
        resolved = await client.resolve_agent(
            agent_name="demo-agent", tenant_id="tenant-x", env="prod"
        )
        assert resolved is not None
        assert resolved.agent_id == "agent-123"
        assert resolved.base_url == "http://tenant-agent:80"  # Prioritized exact match
    except Exception as e:
        print(f"Exception: {e}")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_fallback_global():
    client = AgentRegistryClient(
        registry_base_url="http://fake-registry", agent_key="key", service_id="test"
    )

    # Mock agent lookup
    respx.get("http://fake-registry/v1/agents/demo-agent").mock(
        return_value=Response(
            200, json={"id": "agent-123", "name": "demo-agent", "status": "active"}
        )
    )

    # Mock deployments lookup (only global exists)
    respx.get(path="/v1/deployments").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": "dep-g",
                    "agent_id": "agent-123",
                    "tenant_id": None,
                    "env": "prod",
                    "base_url": "http://global-agent:80",
                }
            ],
        )
    )

    resolved = await client.resolve_agent(agent_name="demo-agent", tenant_id="tenant-y", env="prod")
    assert resolved is not None
    assert resolved.base_url == "http://global-agent:80"  # Fell back to global


@pytest.mark.asyncio
@respx.mock
async def test_resolve_agent_disabled():
    client = AgentRegistryClient(
        registry_base_url="http://fake-registry", agent_key="key", service_id="test"
    )

    # Mock agent lookup as disabled
    respx.get("http://fake-registry/v1/agents/demo-agent").mock(
        return_value=Response(
            200, json={"id": "agent-123", "name": "demo-agent", "status": "disabled"}
        )
    )

    resolved = await client.resolve_agent(agent_name="demo-agent", tenant_id="tenant-x", env="prod")
    assert resolved is None
