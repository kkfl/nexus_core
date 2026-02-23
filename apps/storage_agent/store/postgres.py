import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship

from apps.storage_agent.config import get_settings

logger = structlog.get_logger(__name__)

Base = declarative_base()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class StorageTarget(Base):
    __tablename__ = "storage_targets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=True)  # null = global platform target
    env = Column(String, nullable=False, default="prod")
    storage_target_id = Column(String, nullable=False)
    endpoint_url = Column(String, nullable=True)
    region = Column(String, nullable=True)
    default_bucket = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    credential_aliases = Column(JSONB, server_default="{}", nullable=False)
    flags = Column(JSONB, server_default="{}", nullable=False)
    created_at = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime, server_default=text("now()"), nullable=False)

    buckets = relationship("StorageBucket", back_populates="target", cascade="all, delete-orphan")
    objects = relationship("StorageObject", back_populates="target", cascade="all, delete-orphan")


class StorageBucket(Base):
    __tablename__ = "storage_buckets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=True)
    env = Column(String, nullable=False, default="prod")
    target_id = Column(String, ForeignKey("storage_targets.id", ondelete="CASCADE"), nullable=False)
    bucket_name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime, server_default=text("now()"), nullable=False)

    target = relationship("StorageTarget", back_populates="buckets")
    objects = relationship("StorageObject", back_populates="bucket", cascade="all, delete-orphan")


class StorageObject(Base):
    __tablename__ = "storage_objects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=True)
    env = Column(String, nullable=False, default="prod")
    target_id = Column(String, ForeignKey("storage_targets.id", ondelete="CASCADE"), nullable=False)
    bucket_id = Column(String, ForeignKey("storage_buckets.id", ondelete="CASCADE"), nullable=False)
    object_key = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    checksum = Column(String, nullable=True)
    tags = Column(JSONB, server_default="{}", nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime, server_default=text("now()"), nullable=False)

    target = relationship("StorageTarget", back_populates="objects")
    bucket = relationship("StorageBucket", back_populates="objects")


class StorageJob(Base):
    __tablename__ = "storage_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, nullable=True)
    env = Column(String, nullable=False, default="prod")
    action = Column(String, nullable=False)
    payload = Column(JSONB, server_default="{}", nullable=False)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime, server_default=text("now()"), nullable=False)

    result = relationship(
        "StorageJobResult", back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class StorageJobResult(Base):
    __tablename__ = "storage_job_results"

    job_id = Column(String, ForeignKey("storage_jobs.id", ondelete="CASCADE"), primary_key=True)
    output_summary = Column(JSONB, server_default="{}", nullable=False)
    completed_at = Column(DateTime, server_default=text("now()"), nullable=False)

    job = relationship("StorageJob", back_populates="result")


class StorageAuditEvent(Base):
    __tablename__ = "storage_audit_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    correlation_id = Column(String, nullable=False)
    service_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    env = Column(String, nullable=False, default="prod")
    action = Column(String, nullable=False)
    target_id = Column(String, ForeignKey("storage_targets.id", ondelete="SET NULL"), nullable=True)
    result = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=text("now()"), nullable=False)


# ---------------------------------------------------------------------------
# Global Session & Initialization
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_size=10,
            max_overflow=20,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    _get_engine()
    async with _session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Repository Operations
# ---------------------------------------------------------------------------


async def log_audit(
    db: AsyncSession,
    correlation_id: str,
    service_id: str,
    tenant_id: str | None,
    env: str,
    action: str,
    target_id: str | None,
    result: str,
    detail: str | None = None,
):
    evt = StorageAuditEvent(
        id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        target_id=target_id,
        result=result,
        detail=detail,
    )
    db.add(evt)
    await db.commit()


async def get_target(
    db: AsyncSession, storage_target_id: str, tenant_id: str = "nexus", env: str = "prod"
) -> StorageTarget | None:
    q = select(StorageTarget).where(
        StorageTarget.storage_target_id == storage_target_id,
        StorageTarget.tenant_id == tenant_id,
        StorageTarget.env == env,
        StorageTarget.enabled is True,
    )
    res = await db.execute(q)
    return res.scalars().first()


async def list_targets(
    db: AsyncSession, tenant_id: str = "nexus", env: str = "prod"
) -> list[StorageTarget]:
    q = select(StorageTarget).where(StorageTarget.tenant_id == tenant_id, StorageTarget.env == env)
    res = await db.execute(q)
    return list(res.scalars().all())


async def upsert_target(
    db: AsyncSession,
    tenant_id: str,
    env: str,
    storage_target_id: str,
    endpoint_url: str,
    region: str,
    default_bucket: str,
    credential_aliases: dict,
    flags: dict,
) -> StorageTarget:
    t = await get_target(db, storage_target_id, tenant_id, env)
    if not t:
        t = StorageTarget(
            id=str(uuid.uuid4()), tenant_id=tenant_id, env=env, storage_target_id=storage_target_id
        )
        db.add(t)

    t.endpoint_url = endpoint_url
    t.region = region
    t.default_bucket = default_bucket
    t.credential_aliases = credential_aliases
    t.flags = flags
    t.updated_at = datetime.now(UTC).replace(tzinfo=None)

    await db.flush()
    return t


async def get_or_create_bucket(
    db: AsyncSession, target_id: str, bucket_name: str, tenant_id: str, env: str
) -> StorageBucket:
    q = select(StorageBucket).where(
        StorageBucket.target_id == target_id, StorageBucket.bucket_name == bucket_name
    )
    res = await db.execute(q)
    b = res.scalars().first()
    if not b:
        b = StorageBucket(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            env=env,
            target_id=target_id,
            bucket_name=bucket_name,
        )
        db.add(b)
        await db.flush()
    return b


async def register_object(
    db: AsyncSession,
    tenant_id: str,
    env: str,
    target_id: str,
    bucket_id: str,
    object_key: str,
    content_type: str,
    size_bytes: int,
    tags: dict = None,
    entity_type: str = None,
    entity_id: str = None,
) -> StorageObject:
    # Upsert pattern
    q = select(StorageObject).where(
        StorageObject.target_id == target_id,
        StorageObject.bucket_id == bucket_id,
        StorageObject.object_key == object_key,
    )
    res = await db.execute(q)
    obj = res.scalars().first()

    if not obj:
        obj = StorageObject(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            env=env,
            target_id=target_id,
            bucket_id=bucket_id,
            object_key=object_key,
        )
        db.add(obj)

    obj.content_type = content_type
    obj.size_bytes = size_bytes
    if tags is not None:
        obj.tags = tags
    if entity_type:
        obj.entity_type = entity_type
    if entity_id:
        obj.entity_id = entity_id
    obj.updated_at = datetime.now(UTC).replace(tzinfo=None)

    await db.flush()
    return obj


async def get_object_metadata(db: AsyncSession, object_id: str) -> StorageObject | None:
    q = select(StorageObject).where(StorageObject.id == object_id)
    res = await db.execute(q)
    return res.scalars().first()


async def delete_object_record(
    db: AsyncSession, target_id: str, bucket_id: str, object_key: str
) -> bool:
    q = select(StorageObject).where(
        StorageObject.target_id == target_id,
        StorageObject.bucket_id == bucket_id,
        StorageObject.object_key == object_key,
    )
    res = await db.execute(q)
    obj = res.scalars().first()
    if obj:
        await db.delete(obj)
        return True
    return False
