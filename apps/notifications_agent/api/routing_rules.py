"""POST/GET /v1/routing-rules"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from apps.notifications_agent.auth.identity import ServiceIdentity, get_service_identity, require_admin
from apps.notifications_agent.schemas import RoutingRuleCreate, RoutingRuleOut
from apps.notifications_agent.store import postgres as store

router = APIRouter(prefix="/v1", tags=["routing"])


@router.post("/routing-rules", response_model=RoutingRuleOut, status_code=201)
async def create_routing_rule(
    body: RoutingRuleCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    require_admin(identity)
    rule = await store.upsert_routing_rule(db, **body.model_dump())
    return RoutingRuleOut(id=str(rule.id), tenant_id=rule.tenant_id, env=rule.env,
                          severity=rule.severity, channels=rule.channels,
                          config=rule.config, enabled=rule.enabled, created_at=rule.created_at)


@router.get("/routing-rules", response_model=List[RoutingRuleOut])
async def list_routing_rules(
    tenant_id: str = Query(...),
    env: Optional[str] = Query(None),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    rules = await store.list_routing_rules(db, tenant_id=tenant_id, env=env)
    return [RoutingRuleOut(id=str(r.id), tenant_id=r.tenant_id, env=r.env,
                           severity=r.severity, channels=r.channels,
                           config=r.config, enabled=r.enabled, created_at=r.created_at)
            for r in rules]
