import pytest
from httpx import AsyncClient

from apps.agent_registry.main import app


@pytest.fixture
def registry_headers():
    return {"X-Service-ID": "admin", "X-Agent-Key": "admin-registry-key"}


@pytest.mark.asyncio
async def test_create_and_get_deployment(registry_headers):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create an agent first
        res = await ac.post("/v1/agents", json={"name": "test-dep-agent"}, headers=registry_headers)
        agent_id = res.json()["id"]

        # Create deployment
        dep_data = {
            "agent_id": agent_id,
            "tenant_id": "tenant-abc",
            "env": "prod",
            "base_url": "http://test-agent:8080",
            "auth_scheme": "bearer",
        }
        res_dep = await ac.post("/v1/deployments", json=dep_data, headers=registry_headers)
        assert res_dep.status_code == 201
        created = res_dep.json()
        assert created["agent_id"] == agent_id
        assert created["tenant_id"] == "tenant-abc"
        assert created["base_url"] == "http://test-agent:8080"

        # Get deployments
        res_list = await ac.get(
            "/v1/deployments?env=prod&tenant_id=tenant-abc", headers=registry_headers
        )
        assert res_list.status_code == 200
        deps = res_list.json()
        assert len(deps) > 0
        assert any(d["id"] == created["id"] for d in deps)


@pytest.mark.asyncio
async def test_update_deployment(registry_headers):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post(
            "/v1/agents", json={"name": "test-update-dep-agent"}, headers=registry_headers
        )
        agent_id = res.json()["id"]

        dep_data = {"agent_id": agent_id, "env": "dev", "base_url": "http://dev-agent:8080"}
        res_dep = await ac.post("/v1/deployments", json=dep_data, headers=registry_headers)
        dep_id = res_dep.json()["id"]

        update_data = {"status": "inactive", "base_url": "http://dead-agent:8080"}
        res_patch = await ac.patch(
            f"/v1/deployments/{dep_id}", json=update_data, headers=registry_headers
        )
        assert res_patch.status_code == 200
        updated = res_patch.json()
        assert updated["status"] == "inactive"
        assert updated["base_url"] == "http://dead-agent:8080"
