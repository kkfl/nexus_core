from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import Artifact
from packages.shared.storage import get_storage_backend
from apps.nexus_api.dependencies import get_current_identity, RequireRole

router = APIRouter()

@router.get("/{artifact_id}/download-url")
async def get_artifact_url(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
    current_identity: Any = Depends(get_current_identity)
) -> Any:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalars().first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    storage = get_storage_backend()
    url = storage.get_presigned_url(artifact.object_key)
    
    return {"url": url}
