import os
import json
import logging
import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
import httpx

from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError, ProposedWrite, JobSummary
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="Carrier Agent V1 (SDK)")
logger = logging.getLogger(__name__)

CARRIER_MOCK = os.getenv("CARRIER_MOCK", "false").lower() == "true"
NEXUS_BASE_URL = os.environ.get("NEXUS_BASE_URL", "http://nexus-api:8000")
NEXUS_AGENT_KEY = os.environ.get("NEXUS_AGENT_KEY", "internal-carrier-key-demo")

def load_mock_provider() -> Dict[str, Any]:
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "mock_provider.json"), "r") as f:
        return json.load(f)

async def _fetch_target_and_creds(target_id: str) -> tuple[Dict, str, str]:
    if CARRIER_MOCK and target_id == "mock":
        return {
            "name": "Mock Provider",
            "provider": "mock",
            "id": target_id
        }, "mock_ak", "mock_sk"

    async with httpx.AsyncClient() as client:
        r_meta = await client.get(
            f"{NEXUS_BASE_URL}/internal/carrier/targets/{target_id}",
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY}
        )
        if r_meta.status_code != 200:
            raise Exception(f"Failed to fetch carrier target: {r_meta.text}")
        target = r_meta.json()

        ak = None
        if target.get("api_key_secret_id"):
            r_ak = await client.post(
                f"{NEXUS_BASE_URL}/internal/secrets/decrypt",
                headers={"X-Nexus-Internal": NEXUS_AGENT_KEY},
                json={"secret_id": target["api_key_secret_id"]}
            )
            if r_ak.status_code == 200:
                ak = r_ak.json()["value"]

        sk = None
        if target.get("api_secret_secret_id"):
            r_sk = await client.post(
                f"{NEXUS_BASE_URL}/internal/secrets/decrypt",
                headers={"X-Nexus-Internal": NEXUS_AGENT_KEY},
                json={"secret_id": target["api_secret_secret_id"]}
            )
            if r_sk.status_code == 200:
                sk = r_sk.json()["value"]

    return target, ak, sk

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    persona_received = {"name": req.persona.name, "version": req.persona.version} if req.persona else None
    ctx_count = len(req.context) if req.context else 0

    target_id = req.payload.get("carrier_target_id")
    if not target_id:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="missing_target", message="carrier_target_id is required"))

    # KI persona checking
    allowed = ["carrier.account.status", "carrier.dids.list"]
    if req.persona and req.persona.tools_policy:
        allowed = req.persona.tools_policy.get("allowed_capabilities", allowed)
        
    if req.type not in allowed:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="persona_policy_violation", message=f"{req.type} not in allowed_capabilities"))

    try:
        target, ak, sk = await _fetch_target_and_creds(target_id)
        provider = target.get("provider", "mock")
        
        # In V1, we only implement mock provider
        if provider != "mock":
             return AgentTaskResponse(ok=False, error=AgentTaskError(code="unsupported_provider", message=f"Provider {provider} not fully implemented in V1 (use mock)"))
             
        mock_data = load_mock_provider()

        if req.type == "carrier.account.status":
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "provider": provider,
                "status": "active",
                "balance": 150.00
            }
            return AgentTaskResponse(ok=True, result=result_data)

        elif req.type == "carrier.dids.list":
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "dids": mock_data["dids"],
                "total_count": len(mock_data["dids"])
            }
            return AgentTaskResponse(ok=True, result=result_data)
            
        elif req.type == "carrier.did.lookup":
            number = req.payload.get("number")
            if not number: raise Exception("Missing number")
            
            did = next((d for d in mock_data["dids"] if d["number"] == number), None)
            if not did:
                return AgentTaskResponse(ok=False, error=AgentTaskError(code="not_found", message=f"DID {number} not found"))
                
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "did": did
            }
            return AgentTaskResponse(ok=True, result=result_data)
            
        elif req.type == "carrier.trunks.list":
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "trunks": mock_data["trunks"]
            }
            return AgentTaskResponse(ok=True, result=result_data)
            
        elif req.type == "carrier.messaging.status":
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "messaging_status": mock_data["messaging_status"]
            }
            return AgentTaskResponse(ok=True, result=result_data)
            
        elif req.type == "carrier.cnam.status":
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "cnam_status": mock_data["cnam_status"]
            }
            return AgentTaskResponse(ok=True, result=result_data)
            
        elif req.type == "carrier.snapshot.inventory":
            ts = datetime.datetime.utcnow().timestamp()
            writes = []
            
            # 1. Target Entity
            writes.append(
                ProposedWrite(
                    entity_kind="carrier_target",
                    external_ref=target_id,
                    action="upsert",
                    patch={
                        "name": target.get("name"),
                        "provider": provider,
                        "tags": target.get("tags", []),
                        "last_seen_at": datetime.datetime.utcnow().isoformat()
                    },
                    idempotency_key=f"carrier_target:{target_id}:{ts}"
                )
            )
            
            # 2. DIDs
            for did in mock_data["dids"]:
                writes.append(
                    ProposedWrite(
                        entity_kind="carrier_did",
                        external_ref=f"{target_id}:{did['number']}",
                        action="upsert",
                        patch={
                            "carrier_target_id": target_id,
                            "number": did["number"],
                            "region": did.get("region"),
                            "sms_enabled": did.get("sms_enabled", False),
                            "voice_enabled": did.get("voice_enabled", True),
                            "e911_status": did.get("e911_status"),
                            "assigned_to": did.get("assigned_to"),
                            "tags": did.get("tags", [])
                        },
                        idempotency_key=f"carrier_did:{target_id}:{did['number']}:{ts}"
                    )
                )
                
            # 3. Trunks
            for trunk in mock_data["trunks"]:
                writes.append(
                    ProposedWrite(
                        entity_kind="carrier_trunk",
                        external_ref=f"{target_id}:{trunk['trunk_id']}",
                        action="upsert",
                        patch={
                            "carrier_target_id": target_id,
                            "trunk": trunk["trunk_id"],
                            "status": trunk.get("status"),
                            "tags": trunk.get("tags", [])
                        },
                        idempotency_key=f"carrier_trunk:{target_id}:{trunk['trunk_id']}:{ts}"
                    )
                )
                
            # 4. Messaging
            writes.append(
                ProposedWrite(
                    entity_kind="carrier_messaging",
                    external_ref=f"{target_id}:messaging",
                    action="upsert",
                    patch={
                        "carrier_target_id": target_id,
                        "status_summary": mock_data["messaging_status"]
                    },
                    idempotency_key=f"carrier_messaging:{target_id}:{ts}"
                )
            )
            
            # 5. CNAM
            writes.append(
                ProposedWrite(
                    entity_kind="carrier_cnam",
                    external_ref=f"{target_id}:cnam",
                    action="upsert",
                    patch={
                        "carrier_target_id": target_id,
                        "status_summary": mock_data["cnam_status"]
                    },
                    idempotency_key=f"carrier_cnam:{target_id}:{ts}"
                )
            )

            job_summary = JobSummary(
                kind="carrier_snapshot",
                status="succeeded",
                details={
                    "dids_count": len(mock_data["dids"]),
                    "trunks_count": len(mock_data["trunks"])
                }
            )
            
            result_data = {
                "persona_received": persona_received,
                "context_received_count": ctx_count,
                "snapshot_status": "generated"
            }
            return AgentTaskResponse(ok=True, result=result_data, proposed_writes=writes, job_summary=job_summary)

        else:
             return AgentTaskResponse(ok=False, error=AgentTaskError(code="unknown_task", message=f"Task {req.type} not supported"))

    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="execution_failed", message=str(e)))


@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(req: AgentTaskRequest, request: Request):
    return await handle_agent_execute(req, request, _execute_handler)

@app.get("/capabilities")
async def get_capabilities():
    return {
        "capabilities": [
            "carrier.account.status",
            "carrier.dids.list",
            "carrier.did.lookup",
            "carrier.trunks.list",
            "carrier.messaging.status",
            "carrier.cnam.status",
            "carrier.snapshot.inventory"
        ],
        "version": "1.0.0"
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
