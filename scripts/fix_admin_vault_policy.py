import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        from sqlalchemy import text

        query = text("""
            INSERT INTO vault_policies (id, name, service_id, alias_pattern, actions, is_active)
            VALUES (gen_random_uuid(), 'nexus-all', 'nexus', '*', '["read", "write", "list_metadata"]', true)
            ON CONFLICT (name) DO UPDATE SET actions = '["read", "write", "list_metadata"]', service_id = 'nexus';
        """)
        await conn.execute(query)
        print("Updated Vault policies for nexus")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
