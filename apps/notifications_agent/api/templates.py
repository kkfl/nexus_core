"""POST/GET /v1/templates"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from apps.notifications_agent.auth.identity import ServiceIdentity, get_service_identity, require_admin
from apps.notifications_agent.schemas import TemplateCreate, TemplateOut
from apps.notifications_agent.store import postgres as store

router = APIRouter(prefix="/v1", tags=["templates"])


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    require_admin(identity)
    t = await store.upsert_template(db, **body.model_dump())
    return TemplateOut(id=t.id, name=t.name, channel=t.channel,
                       subject_template=t.subject_template, body_template=t.body_template,
                       storage_policy=t.storage_policy, created_at=t.created_at)


@router.get("/templates", response_model=List[TemplateOut])
async def list_templates(
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    templates = await store.list_templates(db)
    return [TemplateOut(id=t.id, name=t.name, channel=t.channel,
                        subject_template=t.subject_template, body_template=t.body_template,
                        storage_policy=t.storage_policy, created_at=t.created_at)
            for t in templates]
