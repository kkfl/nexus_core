import asyncio
import httpx
import sys
import asyncpg

NEXUS_API_URL = "http://localhost:8000"
REGISTRY_URL = "http://localhost:8012"
VAULT_URL = "http://localhost:8007"
VAULT_ADMIN_KEY = "admin-vault-key-change-me-in-production"

async def run_setup():
    print("=== Nexus V1 Storage Agent Setup ===")

    # 0. Setup Registry
    print("\n0. Setting up storage-agent in Registry Database...")
    conn = await asyncpg.connect("postgresql://nexus:nexus_pass@localhost:5432/nexus_core")
    try:
        q1 = """
        INSERT INTO registry_agents (id, name, description, status, created_at, updated_at)
        VALUES (gen_random_uuid(), 'storage-agent', 'Storage Integration Observer', 'active', now(), now())
        ON CONFLICT (name) DO NOTHING;
        """
        await conn.execute(q1)
        
        await conn.execute("DELETE FROM registry_deployments WHERE agent_id = (SELECT id FROM registry_agents WHERE name = 'storage-agent') AND env = 'prod';")
        
        q2 = """
        INSERT INTO registry_deployments (id, agent_id, env, base_url, version, auth_scheme, auth_secret_alias, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            (SELECT id FROM registry_agents WHERE name = 'storage-agent'),
            'prod',
            'http://storage-agent:8005',
            '1.0.0',
            'nexus-v1',
            'storage-agent.automation-agent.key',
            now(),
            now()
        );
        """
        await conn.execute(q2)

        # 0.5 Setup Vault Policy for storage-agent
        print("  - Inserting storage-agent vault policy...")
        q_policy = """
        INSERT INTO vault_policies (id, name, service_id, alias_pattern, tenant_id, env, actions, priority, is_active)
        VALUES (
            gen_random_uuid(),
            'storage-agent-read',
            'storage-agent',
            '*',
            NULL,
            NULL,
            '["read", "list_metadata"]'::jsonb,
            100,
            true
        )
        ON CONFLICT (name) DO UPDATE SET tenant_id = NULL, env = NULL;
        """
        await conn.execute(q_policy)

    finally:
        await conn.close()

    async with httpx.AsyncClient(timeout=10.0) as client:

        # 1. Setup Vault Secrets for 'minio_local' test target
        print("\n1. Seeding Vault Secrets for minio_local target...")
        secrets = [
            {"alias": "storage.minio_local.access_key_id", "value": "admin"},
            {"alias": "storage.minio_local.secret_access_key", "value": "minio_pass"}
        ]
        
        for s in secrets:
             payload = {
                 "alias": s["alias"],
                 "value": s["value"],
                 "tenant_id": "nexus",
                 "env": "prod",
                 "description": f"S3 Credential for minio_local target"
             }
             resp = await client.post(
                 f"{VAULT_URL}/v1/secrets",
                 json=payload,
                 headers={"X-Service-ID": "admin", "X-Agent-Key": VAULT_ADMIN_KEY}
             )
             if resp.status_code in (200, 201, 409):
                 print(f"  [+] Secret '{s['alias']}' created/updated.")
             else:
                 print(f"  [!] Failed to create secret '{s['alias']}': {resp.status_code} - {resp.text}")

        # 3. Register automation-agent secret credential down into Vault for monitoring to use
        print("\n3. Seeding Storage Agent automation-agent key...")
        aa_payload = {
            "alias": "storage-agent.automation-agent.key",
            "value": "automation-storage-key-change-me",
            "tenant_id": "nexus",
            "env": "prod",
            "description": "Auth token used by automation-agent to call storage-agent"
        }
        resp = await client.post(
            f"{VAULT_URL}/v1/secrets",
            json=aa_payload,
            headers={"X-Service-ID": "admin", "X-Agent-Key": VAULT_ADMIN_KEY}
        )
        if resp.status_code in (200, 201):
             print("  [+] Auth secret 'storage-agent.automation-agent.key' seeded.")
        else:
             print(f"  [!] Failed to seed auth secret: {resp.status_code} - {resp.text}")
             
        print("\n[✔] Setup Script Complete.")


if __name__ == "__main__":
    asyncio.run(run_setup())
