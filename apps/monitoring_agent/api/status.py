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

@router.post("/status/dispatch-digest")
async def dispatch_daily_digest(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    import uuid
    from datetime import datetime, timezone, timedelta
    from apps.monitoring_agent.engine.alerter import dispatch_alert
    
    correlation_id = str(uuid.uuid4())
    
    # Get current targets
    stmt = select(MonitoringTarget, MonitoringState).join(
        MonitoringState, MonitoringTarget.id == MonitoringState.target_id
    )
    if tenant_id: stmt = stmt.where(MonitoringTarget.tenant_id == tenant_id)
    if env: stmt = stmt.where(MonitoringTarget.env == env)
        
    targets_res = await db.execute(stmt)
    records = targets_res.all()
    
    total = len(records)
    up_count = sum(1 for _, s in records if s.current_state == "UP")
    down_count = total - up_count
    
    agent_lines = []
    for t, s in records:
        icon = "✅" if s.current_state == "UP" else "❌"
        agent_lines.append(f"{icon} {t.agent_name} ({s.current_state})")
        
    agents_summary = "\n".join(agent_lines)
    
    # Get recent incidents (last 24 hours)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    inc_stmt = select(MonitoringAuditEvent).where(
        MonitoringAuditEvent.action.in_(["state_change", "alert_dispatched"]),
        MonitoringAuditEvent.created_at >= yesterday
    ).order_by(desc(MonitoringAuditEvent.created_at)).limit(5)
    
    if tenant_id: inc_stmt = inc_stmt.where(MonitoringAuditEvent.tenant_id == tenant_id)
    if env: inc_stmt = inc_stmt.where(MonitoringAuditEvent.env == env)
        
    inc_res = await db.execute(inc_stmt)
    incidents = inc_res.scalars().all()
    
    incident_lines = []
    if not incidents:
        incident_lines.append("No incidents recorded in the last 24 hours.")
    else:
        for inc in incidents:
            action = inc.action
            detail = inc.detail or "No detail"
            time_str = inc.created_at.strftime("%H:%M UTC")
            incident_lines.append(f"- {time_str} | {action}: {detail}")
            
    incidents_summary = "\n".join(incident_lines)
    
    message = (
        f"*Daily System Digest*\n\n"
        f"Overall: {up_count}/{total} Targets UP\n\n"
        f"*Target Status*\n{agents_summary}\n\n"
        f"*Recent Incidents (Last 24h)*\n{incidents_summary}"
    )
    
    # Create a dummy target object to route the alert cleanly using the existing alerter
    dummy = MonitoringTarget(tenant_id=tenant_id, env=env, agent_name="Nexus Platform Root", base_url="")
    await dispatch_alert(dummy, "info", message, correlation_id)
    
    return {"status": "dispatched", "message_length": len(message), "correlation_id": correlation_id}
