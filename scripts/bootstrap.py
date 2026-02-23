import asyncio

from sqlalchemy.future import select

from apps.nexus_api.dependencies import get_password_hash
from packages.shared.db import get_db_context
from packages.shared.models import User


async def bootstrap():
    async with get_db_context() as db:
        # Check if admin exists
        res = await db.execute(select(User).where(User.email == "admin@nexus.local"))
        admin = res.scalars().first()

        if admin:
            print("Admin user already exists.")
            return

        password = "admin_password"
        print(f"Creating default admin user: admin@nexus.local / {password}")

        new_admin = User(
            email="admin@nexus.local",
            password_hash=get_password_hash(password),
            role="admin",
            is_active=True,
        )
        db.add(new_admin)
        await db.commit()
        print("Bootstrap complete!")


if __name__ == "__main__":
    asyncio.run(bootstrap())
