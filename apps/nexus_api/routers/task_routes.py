from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireModuleAccess
from packages.shared.db import get_db
from packages.shared.models import TaskRoute
from packages.shared.schemas.core import TaskRouteCreate, TaskRouteOut, TaskRouteUpdate

router = APIRouter()


@router.post("/", response_model=TaskRouteOut)
async def create_task_route(
    route_in: TaskRouteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireModuleAccess("orchestration", "manage")),
) -> Any:
    db_route = TaskRoute(
        task_type=route_in.task_type,
        required_capabilities=route_in.required_capabilities,
        preferred_agent_id=route_in.preferred_agent_id,
        is_active=route_in.is_active,
    )
    db.add(db_route)
    try:
        await db.commit()
        await db.refresh(db_route)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not create given task route: {e}")
    return db_route


@router.get("/", response_model=list[TaskRouteOut])
async def read_task_routes(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireModuleAccess("orchestration", "read")),
) -> Any:
    res = await db.execute(select(TaskRoute).offset(skip).limit(limit))
    return res.scalars().all()


@router.patch("/{route_id}", response_model=TaskRouteOut)
async def update_task_route(
    route_id: int,
    route_in: TaskRouteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireModuleAccess("orchestration", "manage")),
) -> Any:
    res = await db.execute(select(TaskRoute).where(TaskRoute.id == route_id))
    route = res.scalars().first()
    if not route:
        raise HTTPException(status_code=404, detail="TaskRoute not found")

    update_data = route_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(route, field, value)

    await db.commit()
    await db.refresh(route)
    return route
