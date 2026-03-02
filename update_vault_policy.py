import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DATABASE_URL = "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"


async def update_policy():
    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session, session.begin():
        # Update portal-all policy
        actions = ["read", "write", "rotate", "list_metadata", "delete"]
        query = text("UPDATE vault_policies SET actions = :actions WHERE name = 'portal-all'")
        await session.execute(query, {"actions": json.dumps(actions)})
        print("Successfully updated 'portal-all' policy.")


if __name__ == "__main__":
    asyncio.run(update_policy())
