import os
import json
import logging
import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, Request
from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError, ProposedWrite, ProposedTask
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="Monitoring Agent V1 (SDK)")
logger = logging.getLogger(__name__)

MONITORING_MOCK = os.getenv("MONITORING_MOCK", "false").lower() == "true"
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def _parse_statusjson(raw_data: Any) -> tuple[List[Dict], List[Dict]]:
    # Simple extraction of hosts and services from standard Nagios statusjson
    hosts = []
    services = []
    
    # In mock or raw, it might be a direct dict
    data = raw_data
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            pass
            
    if isinstance(data, dict):
        if "data" in data and "hostlist" in data["data"]:
            hl = data["data"]["hostlist"]
            for hname, hdata in hl.items():
                state_val = hdata.get("status", 0)
                state_str = "UNKNOWN"
                if state_val == 2: state_str = "OK"
                elif state_val == 4: state_str = "CRITICAL" # simplifications
                elif state_val == 8: state_str = "WARNING"
                
                hosts.append({
                    "host": hname,
                    "state": state_str,
                    "output": hdata.get("plugin_output", ""),
                    "last_check_at": hdata.get("last_check", 0) # epoch or iso
                })
        
        if "data" in data and "servicelist" in data["data"]:
            sl = data["data"]["servicelist"]
            for hname, sdata in sl.items():
                for sname, sdetail in sdata.items():
                    state_val = sdetail.get("status", 0)
                    state_str = "UNKNOWN"
                    if state_val == 2: state_str = "OK"
                    elif state_val == 4: state_str = "WARNING"
                    elif state_val == 16: state_str = "CRITICAL"
                    
                    services.append({
                        "host": hname,
                        "service": sname,
                        "state": state_str,
                        "output": sdetail.get("plugin_output", ""),
                        "last_check_at": sdetail.get("last_check", 0)
                    })
    return hosts, services

def _parse_ndjson(raw_data: str) -> tuple[List[Dict], List[Dict]]:
    hosts = []
    services = []
    for line in raw_data.splitlines():
        if not line.strip(): continue
        try:
            item = json.loads(line)
            if item.get("type") == "host":
                hosts.append(item)
            elif item.get("type") == "service":
                services.append(item)
        except json.JSONDecodeError:
            continue
    return hosts, services

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    source_id = req.payload.get("monitoring_source_id")
    if not source_id:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="missing_source", message="monitoring_source_id is required"))

    persona_received = {"name": req.persona.name, "version": req.persona.version} if req.persona else None
    ctx_count = len(req.context) if req.context else 0

    hosts = []
    services = []
    
    create_tasks = req.payload.get("create_tasks_on_alert", False)

    try:
        if req.type == "monitoring.ingest.nagios.statusjson":
            payload_data = req.payload.get("statusjson")
            if MONITORING_MOCK and not payload_data:
                with open(os.path.join(FIXTURES_DIR, "statusjson.json"), "r") as f:
                    payload_data = json.load(f)
            hosts, services = _parse_statusjson(payload_data)
            
        elif req.type == "monitoring.ingest.nagios.ndjson":
            payload_data = req.payload.get("ndjson", "")
            if MONITORING_MOCK and not payload_data:
                with open(os.path.join(FIXTURES_DIR, "data.ndjson"), "r") as f:
                    payload_data = f.read()
            hosts, services = _parse_ndjson(payload_data)
            
        elif req.type == "monitoring.snapshot":
            pass # V1 no-op or explicit pull
            
        elif req.type == "monitoring.alert_to_task":
            # For direct invocation, handled via workflow usually.
            pass
        else:
             return AgentTaskResponse(ok=False, error=AgentTaskError(code="unknown_task", message=f"Task {req.type} not supported"))

        proposed_writes = []
        proposed_tasks = []
        
        iso_now = datetime.datetime.utcnow().isoformat()
        
        for h in hosts:
            hstate = h.get("state", "UNKNOWN")
            hcheck = h.get("last_check_at", iso_now)
            pw = ProposedWrite(
                entity_kind="mon_host",
                external_ref=f"{source_id}:{h.get('host')}",
                action="upsert",
                patch={
                    "monitoring_source_id": source_id,
                    "host": h.get("host"),
                    "state": hstate,
                    "output": h.get("output", ""),
                    "last_check_at": hcheck
                },
                idempotency_key=f"mon:{source_id}:{h.get('host')}:{h.get('host')}:{hstate}:{hcheck}"
            )
            proposed_writes.append(pw)
            
            if create_tasks and hstate in ("WARNING", "CRITICAL"):
                pt = ProposedTask(
                    type="triage.alert",
                    priority="high" if hstate == "CRITICAL" else "normal",
                    payload={
                        "source_id": source_id,
                        "host": h.get("host"),
                        "service": "HOST_STATE",
                        "state": hstate,
                        "output": h.get("output", ""),
                        "last_check_at": str(hcheck)
                    },
                    persona_version_id=req.persona.id if req.persona else None, # preserve persona or allow route to default
                    idempotency_key=f"alert-task:{source_id}:{h.get('host')}:HOST_STATE:{hstate}:{hcheck}"
                )
                proposed_tasks.append(pt)

        for s in services:
            sstate = s.get("state", "UNKNOWN")
            scheck = s.get("last_check_at", iso_now)
            pw = ProposedWrite(
                entity_kind="mon_service",
                external_ref=f"{source_id}:{s.get('host')}:{s.get('service')}",
                action="upsert",
                patch={
                    "monitoring_source_id": source_id,
                    "host": s.get("host"),
                    "service": s.get("service"),
                    "state": sstate,
                    "output": s.get("output", ""),
                    "last_check_at": scheck
                },
                idempotency_key=f"mon:{source_id}:{s.get('host')}:{s.get('service')}:{sstate}:{scheck}"
            )
            proposed_writes.append(pw)
            
            if create_tasks and sstate in ("WARNING", "CRITICAL"):
                pt = ProposedTask(
                    type="triage.alert",
                    priority="high" if sstate == "CRITICAL" else "normal",
                    payload={
                        "source_id": source_id,
                        "host": s.get("host"),
                        "service": s.get("service"),
                        "state": sstate,
                        "output": s.get("output", ""),
                        "last_check_at": str(scheck)
                    },
                    persona_version_id=req.persona.id if req.persona else None,
                    idempotency_key=f"alert-task:{source_id}:{s.get('host')}:{s.get('service')}:{sstate}:{scheck}"
                )
                proposed_tasks.append(pt)

        result_data = {
            "persona_received": persona_received,
            "context_received_count": ctx_count,
            "hosts_processed": len(hosts),
            "services_processed": len(services),
            "alerts_evaluated": create_tasks
        }

        # Also log the ingest execution
        pw_ingest = ProposedWrite(
            entity_kind="monitoring_ingest",
            external_ref=f"ingest:{req.task_id}",
            action="upsert",
            patch={
                "monitoring_source_id": source_id,
                "task_id": int(req.task_id),
                "summary": result_data
            },
            idempotency_key=f"mon-log:{req.task_id}"
        )
        proposed_writes.append(pw_ingest)

        return AgentTaskResponse(
            ok=True,
            result=result_data,
            proposed_writes=proposed_writes if proposed_writes else None,
            proposed_tasks=proposed_tasks if proposed_tasks else None
        )

    except Exception as e:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="ingest_failed", message=str(e)))

@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(req: AgentTaskRequest, request: Request):
    return await handle_agent_execute(req, request, _execute_handler)

@app.get("/capabilities")
async def get_capabilities():
    return {
        "capabilities": [
            "monitoring.ingest.nagios.statusjson",
            "monitoring.ingest.nagios.ndjson",
            "monitoring.snapshot",
            "monitoring.alert_to_task"
        ],
        "version": "1.0.0"
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
