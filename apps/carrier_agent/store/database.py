from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from apps.carrier_agent.models import Base
from apps.carrier_agent.config import config

engine = create_async_engine(config.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with async_session() as session:
        yield session
