from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from packages.shared.models.core import AuditEvent, User, Agent

def log_audit_event(
    db: AsyncSession,
    action: str,
    resource_type: str,
    identity: Any = None,
    resource_id: Optional[str] = None,
    meta_data: Optional[Dict[str, Any]] = None
) -> None:
    actor_id = None
    actor_type = None
    
    if identity:
        if isinstance(identity, User):
            actor_id = identity.id
            actor_type = "user"
        elif isinstance(identity, Agent):
            actor_id = identity.id
            actor_type = "agent"
            
    event = AuditEvent(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=resource_type,
        target_id=int(resource_id) if resource_id else 0,
        meta_data=meta_data or {}
    )
    db.add(event)
