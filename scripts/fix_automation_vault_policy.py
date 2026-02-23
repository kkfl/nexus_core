import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        from sqlalchemy import text

        # Give automation-agent permission to read any downstream agent API key
        query = text("""
            INSERT INTO vault_policies (id, name, service_id, alias_pattern, tenant_id, env, actions, is_active)
            VALUES (gen_random_uuid(), 'automation-agent-downstream', 'automation-agent', '*.key', NULL, NULL, '["read", "list_metadata"]', true)
            ON CONFLICT (name) DO UPDATE SET actions = '["read", "list_metadata"]';
        """)
        await conn.execute(query)
        print("Updated Vault policies for automation-agent")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
