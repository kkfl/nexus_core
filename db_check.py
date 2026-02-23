import asyncio

import asyncpg

DATABASE_URL = "postgresql://nexus:nexus_pass@localhost:5432/nexus_core"


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        "SELECT a.name, d.base_url FROM registry_agents a JOIN registry_deployments d ON a.id = d.agent_id ORDER BY a.name;"
    )
    for r in rows:
        print(f"{r['name']:<25} | {r['base_url']}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
