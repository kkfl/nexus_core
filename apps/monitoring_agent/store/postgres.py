"""
Postgres DB Models and CRUD for Monitoring Agent
"""
from datetime import datetime, timezone
import json
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey, text, desc, update
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from apps.monitoring_agent.config import get_settings

Base = declarative_base()

class MonitoringTarget(Base):
    __tablename__ = "monitoring_targets"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=True) # null = global platform agent
    env = Column(String, nullable=False, default="prod")
    agent_name = Column(String, nullable=False)
    deployment_id = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    tags = Column(JSONB, server_default='[]', nullable=True)
    created_at = Column(DateTime, server_default=text('now()'), nullable=False)
    updated_at = Column(DateTime, server_default=text('now()'), nullable=False)

    state = relationship("MonitoringState", back_populates="target", uselist=False, cascade="all, delete-orphan")
    checks = relationship("MonitoringCheck", back_populates="target", cascade="all, delete-orphan")

class MonitoringState(Base):
    __tablename__ = "monitoring_state"

    target_id = Column(String, ForeignKey("monitoring_targets.id", ondelete="CASCADE"), primary_key=True)
    last_seen_at = Column(DateTime, nullable=True)
    current_state = Column(String, nullable=False, default="UP") # UP, DOWN, DEGRADED
    last_state_change_at = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_alerted_at = Column(DateTime, nullable=True)
    alert_cooldown_until = Column(DateTime, nullable=True)

    target = relationship("MonitoringTarget", back_populates="state")

class MonitoringCheck(Base):
    __tablename__ = "monitoring_checks"

    id = Column(String, primary_key=True)
    target_id = Column(String, ForeignKey("monitoring_targets.id", ondelete="CASCADE"), nullable=False)
    correlation_id = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    health_status_code = Column(Integer, nullable=True)
    ready_status_code = Column(Integer, nullable=True)
    health_ok = Column(Boolean, nullable=False)
    ready_ok = Column(Boolean, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    error_code = Column(String, nullable=True)
    error_detail_redacted = Column(String, nullable=True)
    capabilities_hash = Column(String, nullable=True)

    target = relationship("MonitoringTarget", back_populates="checks")

class MonitoringAuditEvent(Base):
    __tablename__ = "monitoring_audit_events"
    id = Column(String, primary_key=True)
    correlation_id = Column(String, nullable=False)
    service_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    env = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_id = Column(String, ForeignKey("monitoring_targets.id", ondelete="SET NULL"), nullable=True)
    result = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=text('now()'), nullable=False)


_engine = None
_session_factory = None

def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        import os
        db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://nexus:nexus_pass@postgres:5432/nexus_core")
        _engine = create_async_engine(db_url, pool_size=10, max_overflow=20)
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine

async def get_db() -> AsyncSession:
    _get_engine()
    async with _session_factory() as session:
        yield session

# -- CRUD operations --

async def get_targets(db: AsyncSession, tenant_id: Optional[str] = None, env: Optional[str] = None) -> List[MonitoringTarget]:
    from sqlalchemy import select
    stmt = select(MonitoringTarget).where(MonitoringTarget.enabled == True)
    if tenant_id is not None:
        stmt = stmt.where(MonitoringTarget.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(MonitoringTarget.env == env)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def upsert_target(db: AsyncSession, target_dict: Dict[str, Any]) -> MonitoringTarget:
    from sqlalchemy import select
    tid = target_dict["id"]
    stmt = select(MonitoringTarget).where(MonitoringTarget.id == tid)
    result = await db.execute(stmt)
    t = result.scalar_one_or_none()
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None) # Alembic models typically store naive UTC

    if not t:
        t = MonitoringTarget(
            id=tid,
            tenant_id=target_dict.get("tenant_id"),
            env=target_dict.get("env", "prod"),
            agent_name=target_dict["agent_name"],
            deployment_id=target_dict["deployment_id"],
            base_url=target_dict["base_url"],
            tags=target_dict.get("tags", []),
        )
        db.add(t)
        # Auto-create state
        state = MonitoringState(target_id=tid, current_state="UP", consecutive_failures=0, last_seen_at=now_dt)
        db.add(state)
    else:
        t.tenant_id = target_dict.get("tenant_id")
        t.env = target_dict.get("env", "prod")
        t.agent_name = target_dict["agent_name"]
        t.deployment_id = target_dict["deployment_id"]
        t.base_url = target_dict["base_url"]
        t.tags = target_dict.get("tags", t.tags)
        t.updated_at = now_dt
        
        # State should exist, but ensure it does
        state_stmt = select(MonitoringState).where(MonitoringState.target_id == tid)
        state_result = await db.execute(state_stmt)
        if not state_result.scalar_one_or_none():
            state = MonitoringState(target_id=tid, current_state="UP", consecutive_failures=0, last_seen_at=now_dt)
            db.add(state)
            
    await db.flush()
    return t

async def get_target_state(db: AsyncSession, target_id: str) -> Optional[MonitoringState]:
    from sqlalchemy import select
    stmt = select(MonitoringState).where(MonitoringState.target_id == target_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()

async def record_check(db: AsyncSession, check: MonitoringCheck):
    db.add(check)
    await db.flush()

async def log_audit(db: AsyncSession, correlation_id: str, service_id: str, tenant_id: Optional[str], env: str, action: str, result: str, target_id: Optional[str] = None, detail: str = None):
    import uuid
    evt = MonitoringAuditEvent(
        id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        result=result,
        target_id=target_id,
        detail=detail
    )
    db.add(evt)
    await db.flush()
