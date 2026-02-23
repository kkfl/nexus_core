import os
import asyncio
import httpx

async def seed_secret():
    headers = {
        "X-Service-ID": "nexus",
        "X-Agent-Key": os.getenv("NEXUS_MASTER_KEY", "<REDACTED_API_KEY>")
    }
    payload = {
        "alias": "monitoring-agent.automation-agent.key",
        "tenant_id": "nexus",
        "env": "prod",
        "value": os.getenv("MONITORING_AUTOMATION_KEY", "<REDACTED_API_KEY>"), 
        "description": "Seeded key for monitoring-agent automations",
        "sensitivity": "high"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:8007/v1/secrets", json=payload, headers=headers)
        if resp.status_code in (200, 201):
            print("Secret successfully written via API.")
        elif resp.status_code == 409:
            print("Secret already exists.")
        else:
            print(f"Failed to create secret: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    asyncio.run(seed_secret())
