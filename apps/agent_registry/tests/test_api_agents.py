import pytest
from httpx import AsyncClient

from apps.agent_registry.main import app

@pytest.fixture
def registry_headers():
    return {
        "X-Service-ID": "admin",
        "X-Agent-Key": "admin-registry-key"
    }

@pytest.mark.asyncio
async def test_create_and_get_agent(registry_headers):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create
        agent_data = {
            "name": "test-agent",
            "description": "A test agent"
        }
        res = await ac.post("/v1/agents", json=agent_data, headers=registry_headers)
        assert res.status_code == 201
        created = res.json()
        assert created["name"] == "test-agent"
        assert created["description"] == "A test agent"
        assert "id" in created

        # Get
        res_get = await ac.get(f"/v1/agents/{created['id']}", headers=registry_headers)
        assert res_get.status_code == 200
        fetched = res_get.json()
        assert fetched["id"] == created["id"]
        assert fetched["name"] == "test-agent"

@pytest.mark.asyncio
async def test_update_agent(registry_headers):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        agent_data = {"name": "update-agent"}
        res = await ac.post("/v1/agents", json=agent_data, headers=registry_headers)
        agent_id = res.json()["id"]

        update_data = {"status": "disabled", "description": "Offline"}
        res_patch = await ac.patch(f"/v1/agents/{agent_id}", json=update_data, headers=registry_headers)
        assert res_patch.status_code == 200
        updated = res_patch.json()
        assert updated["status"] == "disabled"
        assert updated["description"] == "Offline"

@pytest.mark.asyncio
async def test_unauthorized_access():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/v1/agents", headers={"X-Service-ID": "bad", "X-Agent-Key": "bad"})
        assert res.status_code == 401
