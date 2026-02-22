import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.models import Entity, EntityEvent, IdempotencyKey
from packages.shared.schemas.agent_sdk import ProposedWrite

class SoRValidationError(Exception):
    def __init__(self, detail: str, code: str = "sor_validation_failed"):
        self.detail = detail
        self.code = code
        super().__init__(self.detail)

# A) Allowlist of entity kinds
ALLOWED_ENTITIES = {
    "dns_record": {
        "required_fields": ["name", "record_type", "value", "ttl"]
    }
}

def validate_proposed_write(write: ProposedWrite):
    if write.entity_kind not in ALLOWED_ENTITIES:
        raise SoRValidationError(f"Entity kind {write.entity_kind} not allowed.", "sor_kind_denied")
        
    config = ALLOWED_ENTITIES[write.entity_kind]
    for field in config["required_fields"]:
        if field not in write.patch:
            raise SoRValidationError(f"Missing required field {field} for {write.entity_kind}", "sor_validation_failed")

async def check_idempotency(db: AsyncSession, key: str, scope: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Checks if an idempotency key exists.
    If it exists and payload hashes match, return the stored response.
    If it exists but hashes differ, raise a conflict error.
    If it does not exist, return None.
    """
    data_str = json.dumps(request_data, sort_keys=True)
    req_hash = hashlib.sha256(data_str.encode()).hexdigest()
    
    res = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    idem_record = res.scalars().first()
    
    if idem_record:
        if idem_record.request_hash == req_hash:
            return idem_record.response
        else:
            raise SoRValidationError("Idempotency conflict: key reused with different payload.", "idempotency_conflict")
            
    return None

def apply_json_merge_patch(target: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Simplified JSON merge patch."""
    res = dict(target)
    for k, v in patch.items():
        if v is None:
            res.pop(k, None)
        else:
            res[k] = v
    return res
