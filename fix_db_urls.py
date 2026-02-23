import asyncio
import asyncpg
import os

DATABASE_URL = "postgresql://nexus:nexus_pass@localhost:5432/nexus_core"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE registry_deployments SET base_url = 'http://storage-agent:8005' WHERE base_url = 'http://storage-agent:8002';")
    await conn.execute("UPDATE registry_deployments SET base_url = 'http://pbx-agent:8003' WHERE base_url = 'http://pbx-agent:8011';")
    await conn.execute("UPDATE registry_deployments SET base_url = 'http://monitoring-agent:8004' WHERE base_url = 'http://monitoring-agent:8010';")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
