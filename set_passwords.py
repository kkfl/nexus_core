import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

async def main():
    engine = create_async_engine("postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core")
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    password_str = "password"
    hashed_password = pwd_context.hash(password_str)
    
    print(f"Generated clean hash.")

    async with async_session() as session:
        await session.execute(text(f"UPDATE users SET password_hash = '{hashed_password}' WHERE email = 'rpowell@gsmcall.com'"))
        await session.execute(text(f"UPDATE users SET password_hash = '{hashed_password}' WHERE email = 'admin@nexus.local'"))
        await session.commit()
    
    print("Passwords successfully updated to 'password'.")

if __name__ == "__main__":
    asyncio.run(main())
