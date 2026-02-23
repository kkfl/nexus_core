import asyncio

import httpx

REGISTRY_URL = "http://localhost:8012/v1"
HEADERS = {"X-Service-ID": "admin", "X-Agent-Key": "admin-registry-key"}

EXPECTED_AGENTS = [
    {"name": "secrets-agent", "url": "http://secrets-agent:8007", "auth": "headers"},
    {"name": "dns-agent", "url": "http://dns-agent:8006", "auth": "headers"},
    {"name": "pbx-agent", "url": "http://pbx-agent:8003", "auth": "headers"},
    {"name": "carrier-agent", "url": "http://carrier-agent:8009", "auth": "headers"},
    {"name": "storage-agent", "url": "http://storage-agent:8005", "auth": "headers"},
    {"name": "monitoring-agent", "url": "http://monitoring-agent:8004", "auth": "headers"},
    {"name": "notifications-agent", "url": "http://notifications-agent:8008", "auth": "headers"},
    {"name": "agent_registry", "url": "http://agent-registry:8012", "auth": "headers"},
    {"name": "nexus_api", "url": "http://nexus-api:8000", "auth": "headers"},
]


async def main():
    async with httpx.AsyncClient() as client:
        # 1. Fetch existing agents
        res = await client.get(f"{REGISTRY_URL}/agents", headers=HEADERS)
        existing_agents = res.json()
        agent_names = {a["name"]: a["id"] for a in existing_agents}

        # 2. Register missing agents and deployments
        for expected in EXPECTED_AGENTS:
            if expected["name"] not in agent_names:
                print(f"Adding missing agent: {expected['name']}")
                res = await client.post(
                    f"{REGISTRY_URL}/agents", json={"name": expected["name"]}, headers=HEADERS
                )
                if res.status_code in (200, 201):
                    agent_id = res.json()["id"]
                    print(f"Adding deployment for: {expected['name']}")
                    await client.post(
                        f"{REGISTRY_URL}/deployments",
                        json={
                            "agent_id": agent_id,
                            "env": "prod",
                            "base_url": expected["url"],
                            "auth_scheme": expected["auth"],
                        },
                        headers=HEADERS,
                    )

        # 3. Output Table
        print(
            f"{'agent_name':<20} | {'tenant_id':<10} | {'env':<5} | {'base_url':<30} | {'version':<10} | {'auth_scheme':<12} | {'capabilities_endpoint'}"
        )
        print("-" * 120)

        res = await client.get(f"{REGISTRY_URL}/agents", headers=HEADERS)
        agents = res.json()

        for a in agents:
            deps_res = await client.get(
                f"{REGISTRY_URL}/deployments?agent_id={a['id']}", headers=HEADERS
            )
            deps = deps_res.json()
            if not deps:
                print(
                    f"{a['name']:<20} | <none>     | <none> | <none>                         | <none>     | <none>"
                )
            for d in deps:
                tenant = d.get("tenant_id") or "global"
                env = d.get("env") or "prod"
                print(
                    f"{a['name']:<20} | {tenant:<10} | {env:<5} | {d['base_url']:<30} | {'v1':<10} | {d['auth_scheme']:<12} | /capabilities"
                )


if __name__ == "__main__":
    asyncio.run(main())
