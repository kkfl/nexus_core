from fastapi import FastAPI, Request
import hashlib
from typing import Dict, Any
from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError, ProposedWrite
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="DNS Agent V1 (SDK)")

# In-memory "database" for local DNS
dns_records: Dict[str, Dict[str, str]] = {}

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    print(f"DNS Agent received task {req.task_id} of type {req.type}")
    
    persona_received = None
    if req.persona:
        persona_received = {"name": req.persona.name, "version": req.persona.version}

    if req.type == "dns.lookup":
        name = req.payload.get("name")
        rec_type = req.payload.get("record_type", "A")
        
        ctx_len = len(req.context) if req.context else 0
        
        # 1. Prefer Canonical Entities from Context (if injected by RAG/Worker)
        found_entity = None
        if req.context:
            for ctx_item in req.context:
                if ctx_item.get("kind") == "dns_record" and ctx_item.get("external_ref") == f"{name}:{rec_type}":
                    found_entity = ctx_item.get("data")
                    break
                # Alternatively, just look for matching data from RAG text chunks
                if isinstance(ctx_item, dict) and "text" in ctx_item:
                    # simplistic checking for demo
                    pass
        
        # 2. Fallback to Agent's internal store
        if found_entity:
            result_val = found_entity.get("value")
            source = "nexus_canonical"
        else:
            result_val = dns_records.get(f"{name}_{rec_type}")
            source = "agent_internal"
            
        return AgentTaskResponse(
            ok=True,
            result={
                "name": name,
                "record_type": rec_type,
                "value": result_val,
                "status": "found" if result_val else "not_found",
                "source": source,
                "persona_received": persona_received,
                "context_received_count": ctx_len,
                "context": req.context
            }
        )
        
    elif req.type == "dns.upsert_record":
        name = req.payload.get("name")
        rec_type = req.payload.get("record_type", "A")
        val = req.payload.get("value")
        ttl = req.payload.get("ttl", 300)
        
        if not name or not val:
            return AgentTaskResponse(ok=False, error=AgentTaskError(code="invalid_payload", message="name and value required"))
            
        # Optional: idempotency key from payload or deterministic
        idem_key = req.payload.get("idempotency_key")
        if not idem_key:
            raw_hash = f"{req.task_id}_{name}_{rec_type}_{val}"
            idem_key = hashlib.sha256(raw_hash.encode()).hexdigest()
            
        dns_records[f"{name}_{rec_type}"] = val
        ctx_len = len(req.context) if req.context else 0
        
        pw = ProposedWrite(
            entity_kind="dns_record",
            external_ref=f"{name}:{rec_type}",
            action="upsert",
            patch={"name": name, "record_type": rec_type, "value": val, "ttl": ttl},
            idempotency_key=idem_key
        )
        
        return AgentTaskResponse(
            ok=True,
            result={
                "name": name,
                "record_type": rec_type,
                "value": val,
                "ttl": ttl,
                "status": "upserted",
                "persona_received": persona_received,
                "context_received_count": ctx_len,
                "context": req.context
            },
            proposed_writes=[pw]
        )
    
    return AgentTaskResponse(
        ok=False,
        error=AgentTaskError(code="unknown_task_type", message=f"Unknown task type: {req.type}")
    )


@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(req: AgentTaskRequest, request: Request):
    return await handle_agent_execute(req, request, _execute_handler)


@app.get("/capabilities")
async def get_capabilities():
    return {"capabilities": ["dns.lookup", "dns.upsert_record"], "version": "1.0.0"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
