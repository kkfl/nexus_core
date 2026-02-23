"""
Status REST API
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from apps.monitoring_agent.store.postgres import get_db, MonitoringTarget, MonitoringState, MonitoringCheck, MonitoringAuditEvent

router = APIRouter(prefix="/v1", tags=["status"])

@router.get("/status/current")
async def current_status(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(MonitoringTarget, MonitoringState).join(
        MonitoringState, MonitoringTarget.id == MonitoringState.target_id
    )
    if tenant_id:
        stmt = stmt.where(MonitoringTarget.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(MonitoringTarget.env == env)
        
    result = await db.execute(stmt)
    records = result.all()
    
    return [
        {
            "target_id": t.id,
            "agent_name": t.agent_name,
            "base_url": t.base_url,
            "tenant_id": t.tenant_id,
            "env": t.env,
            "state": s.current_state,
            "last_seen_at": s.last_seen_at,
            "last_state_change_at": s.last_state_change_at,
            "consecutive_failures": s.consecutive_failures
        }
        for t, s in records
    ]

@router.get("/status/history")
async def check_history(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    agent_name: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(MonitoringCheck, MonitoringTarget).join(
        MonitoringTarget, MonitoringCheck.target_id == MonitoringTarget.id
    ).order_by(desc(MonitoringCheck.started_at)).limit(limit)
    
    if tenant_id:
        stmt = stmt.where(MonitoringTarget.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(MonitoringTarget.env == env)
    if agent_name:
        stmt = stmt.where(MonitoringTarget.agent_name == agent_name)
        
    result = await db.execute(stmt)
    records = result.all()
    
    return [
        {
            "check_id": c.id,
            "agent_name": t.agent_name,
            "started_at": c.started_at,
            "ended_at": c.ended_at,
            "health_ok": c.health_ok,
            "ready_ok": c.ready_ok,
            "latency_ms": c.latency_ms,
            "error_code": c.error_code,
            "error_detail": c.error_detail_redacted
        }
        for c, t in records
    ]

@router.get("/incidents")
async def list_incidents(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(MonitoringAuditEvent).where(
        MonitoringAuditEvent.action.in_(["state_change", "alert_dispatched"])
    ).order_by(desc(MonitoringAuditEvent.created_at)).limit(limit)
    
    if tenant_id:
        stmt = stmt.where(MonitoringAuditEvent.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(MonitoringAuditEvent.env == env)
        
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    return [
        {
            "id": e.id,
            "action": e.action,
            "target_id": e.target_id,
            "result": e.result,
            "detail": e.detail,
            "created_at": e.created_at
        }
        for e in events
    ]
