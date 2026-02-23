import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

DATABASE_URL = "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        from sqlalchemy import text
        # Set auth schema and secret alias for monitoring-agent
        query = text("""
            UPDATE registry_deployments 
            SET auth_scheme = 'headers', 
                auth_secret_alias = 'monitoring-agent.automation-agent.key'
            WHERE agent_id IN (SELECT id FROM registry_agents WHERE name = 'monitoring-agent');
        """)
        await conn.execute(query)
        print("Updated monitoring-agent deployment with auth_secret_alias")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
