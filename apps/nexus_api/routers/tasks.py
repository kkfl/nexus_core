from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import Task, TaskRun, User, Agent, PersonaVersion, TaskRoute
from packages.shared.schemas.core import TaskCreate, TaskOut, TaskRunOut
from packages.shared.queue import task_queue
from apps.nexus_api.dependencies import get_current_identity, RequireRole
from packages.shared.policy import enforce_persona_policy
from packages.shared import metrics as metrics_emitter

router = APIRouter()

@router.post("/", response_model=TaskOut)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)  # Can be agent or user
) -> Any:
    req_user_id = current_identity.id if isinstance(current_identity, User) else None
    req_agent_id = current_identity.id if isinstance(current_identity, Agent) else None
    
    # Optional early validation if persona is provided directly
    if task_in.persona_version_id:
        pv_res = await db.execute(select(PersonaVersion).where(PersonaVersion.id == task_in.persona_version_id))
        pv = pv_res.scalars().first()
        if not pv:
            raise HTTPException(status_code=400, detail="Invalid persona_version_id")
            
        route_res = await db.execute(select(TaskRoute).where(TaskRoute.task_type == task_in.type))
        route = route_res.scalars().first()
        req_caps = route.required_capabilities if route else []
        
        if pv.tools_policy:
            enforce_persona_policy(task_in.type, req_caps, None, pv.tools_policy)

    db_task = Task(
        type=task_in.type,
        payload=task_in.payload,
        assigned_agent_id=task_in.assigned_agent_id,
        persona_version_id=task_in.persona_version_id,
        priority=task_in.priority,
        requested_by_user_id=req_user_id,
        requested_by_agent_id=req_agent_id
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    
    await metrics_emitter.emit(db, "task_create", meta={"task_type": db_task.type, "task_id": db_task.id})
    await db.commit()
    
    # Enqueue task to RQ
    task_queue.enqueue(
        "apps.nexus_worker.jobs.dispatch_task", 
        task_id=db_task.id, 
        job_id=f"nexus_task_{db_task.id}"
    )
    
    return db_task

@router.get("/", response_model=List[TaskOut])
async def read_tasks(
    status: Optional[str] = None,
    type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)
) -> Any:
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if type:
        stmt = stmt.where(Task.type == type)
    
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{task_id}", response_model=TaskOut)
async def read_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)
) -> Any:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)
) -> Any:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.status in ['succeeded', 'failed', 'cancelled']:
        raise HTTPException(status_code=400, detail="Terminal status reached")
        
    task.status = "cancelled"
    await db.commit()
    
    # Optionally remove from RQ if it's queued
    # job = Job.fetch(f"nexus_task_{task.id}", connection=redis_conn)
    # job.cancel()
    
    return {"status": "cancelled", "task_id": task_id}

@router.get("/{task_id}/runs")
async def read_task_runs(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)
) -> Any:
    result = await db.execute(select(TaskRun).where(TaskRun.task_id == task_id))
    return result.scalars().all()
