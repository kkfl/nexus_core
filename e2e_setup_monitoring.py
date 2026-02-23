import httpx
import asyncio
import os
import sys

# Minimal script to seed the DB directly with the monitoring agent credentials and setup
async def setup_monitoring_agent():
    print("Setting up monitoring-agent in Registry & Vault...")
    import asyncpg
    
    # Connect directly to the exposed postgres port for Registry inserts
    conn = await asyncpg.connect("postgresql://nexus:nexus_pass@localhost:5432/nexus_core")
    
    try:
        # 1. Register monitoring-agent
        q1 = """
        INSERT INTO registry_agents (id, name, description, status, created_at, updated_at)
        VALUES (gen_random_uuid(), 'monitoring-agent', 'Platform Observer', 'active', now(), now())
        ON CONFLICT (name) DO NOTHING;
        """
        await conn.execute(q1)
        
        # 2. Register monitoring-agent deployment
        q2 = """
        INSERT INTO registry_deployments (id, agent_id, env, base_url, version, auth_scheme, auth_secret_alias, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            (SELECT id FROM registry_agents WHERE name = 'monitoring-agent'),
            'prod',
            'http://monitoring-agent:8004',
            '1.0.0',
            'nexus-v1',
            'monitoring-agent.automation-agent.key',
            now(),
            now()
        ) 
        --- Note: The schema doesn't have a unique constraint that allows ON CONFLICT DO NOTHING for deployments cleanly without a specific unique index.
        --- We will just delete it first if it exists, then insert.
        """
        await conn.execute("DELETE FROM registry_deployments WHERE agent_id = (SELECT id FROM registry_agents WHERE name = 'monitoring-agent') AND env = 'prod';")
        await conn.execute(q2)
    finally:
        await conn.close()

    # 3. Insert secret in Vault using the HTTP API (since the DB requires application-level encryption)
    print("Writing secret to Vault API...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {
                "X-Service-ID": "admin",
                "X-Agent-Key": "admin-vault-key-change-me"
            }
            payload = {
                "alias": "monitoring-agent.automation-agent.key",  # The exact alias monitoring_agent looks for
                "tenant_id": "nexus",
                "env": "prod",
                "value": "automation-monitoring-key-change-me", 
                "description": "Seeded key for monitoring-agent e2e test",
                "sensitivity": "high"
            }
            resp = await client.post("http://localhost:8007/v1/secrets", json=payload, headers=headers)
            if resp.status_code not in (200, 201, 409):
                print(f"Failed to create secret: {resp.status_code} {resp.text}")
            elif resp.status_code == 409:
                print("Secret already exists, skipping...")
            else:
                print("Secret successfully written.")
    except Exception as e:
        print(f"Failed to call secrets agent: {e}")

    print("DB Seed Complete.")

if __name__ == "__main__":
    asyncio.run(setup_monitoring_agent())
