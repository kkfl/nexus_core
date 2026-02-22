import os
import json
import asyncio
import httpx
import re
import hashlib
from typing import Dict, Any, List
from fastapi import FastAPI, Request
from pydantic import BaseModel

from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError, ProposedWrite
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="PBX Agent V1 (SDK)")

# Configuration
NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL", "http://nexus-api:8000")
NEXUS_AGENT_KEY = os.getenv("NEXUS_AGENT_KEY", "dummy-key")
PBX_MOCK = os.getenv("PBX_MOCK", "false").lower() == "true"

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

async def _fetch_pbx_target(target_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{NEXUS_BASE_URL}/internal/pbx/targets/{target_id}",
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY}
        )
        res.raise_for_status()
        return res.json()

async def _decrypt_secret(secret_id: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{NEXUS_BASE_URL}/internal/secrets/decrypt",
            json={"secret_id": secret_id},
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY}
        )
        res.raise_for_status()
        return res.json()["value"]

def _sanitize_output(output: str) -> str:
    """Mask secrets in AMI output."""
    # Mask key=value pairs for sensitive keys
    output = re.sub(r'(?i)(secret|password|md5|auth|token)\s*[:=]\s*[^\n\r]+', r'\1: ***', output)
    # Mask SIP Authorization headers
    output = re.sub(r'(?i)(Authorization:\s*)[^\n\r]+', r'\1***', output)
    
    # Cap size to 200KB
    max_size = 200 * 1024
    if len(output) > max_size:
        output = output[:max_size] + "\n...[TRUNCATED: Exceeds 200KB limit]"
    return output

async def _run_ami_command(command: str, host: str, port: int, username: str, secret: str) -> str:
    if PBX_MOCK:
        # Load from fixture
        cmd_safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', command)
        fixture_path = os.path.join(FIXTURES_DIR, f"{cmd_safe}.txt")
        if os.path.exists(fixture_path):
            with open(fixture_path, 'r') as f:
                return _sanitize_output(f.read())
        return f"Mock output for {command}"

    # Simple AMI execution using asyncio streams
    import telnetlib # Not async but for mock/demo, or use raw sockets
    # For a real implementation, you'd use panoramisk or similar.
    # We'll simulate a basic raw socket connection here for illustrative purposes if not mocked
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5.0)
        
        # Login
        login_cmd = f"Action: Login\r\nUsername: {username}\r\nSecret: {secret}\r\n\r\n"
        writer.write(login_cmd.encode())
        await writer.drain()
        
        # Read until authenticated
        auth_resp = b""
        while b"Message: Authentication" not in auth_resp:
            auth_resp += await asyncio.wait_for(reader.read(1024), timeout=5.0)
            
        # Execute Command
        action_cmd = f"Action: Command\r\nCommand: {command}\r\n\r\n"
        writer.write(action_cmd.encode())
        await writer.drain()
        
        # Read until end of command
        cmd_resp = b""
        while b"--END COMMAND--" not in cmd_resp:
             try:
                 chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                 if not chunk: break
                 cmd_resp += chunk
             except asyncio.TimeoutError:
                 break
                 
        # Logoff
        writer.write(b"Action: Logoff\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        
        return _sanitize_output(cmd_resp.decode(errors='ignore'))
    except Exception as e:
        raise Exception(f"AMI command failed: {str(e)}")

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    target_id = req.payload.get("pbx_target_id")
    if not target_id:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="missing_target", message="pbx_target_id is required"))

    # Validate persona
    persona_received = {"name": req.persona.name, "version": req.persona.version} if req.persona else None
    ctx_count = len(req.context) if req.context else 0

    try:
        target = await _fetch_pbx_target(target_id)
        secret = await _decrypt_secret(target["ami_secret_secret_id"])
    except Exception as e:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="target_fetch_failed", message=str(e)))

    host = target["ami_host"]
    port = target["ami_port"]
    username = target["ami_username"]
    
    # Task specific logic
    result_data = {
        "persona_received": persona_received,
        "context_received_count": ctx_count
    }
    proposed_writes = []

    try:
        if req.type == "pbx.status":
            out = await _run_ami_command("core show uptime", host, port, username, secret)
            result_data["uptime_output"] = out
            
        elif req.type == "pbx.channels.active":
            out = await _run_ami_command("core show channels concise", host, port, username, secret)
            lines = [l for l in out.split('\n') if l.strip()]
            
            # Simple parsing (excluding headers/footers if any)
            channels = len([l for l in lines if '!' in l]) # concise format uses !
            result_data["active_channels"] = channels
            result_data["raw_excerpt"] = "\n".join(lines[:10])
            
        elif req.type == "pbx.endpoints.list":
            out = await _run_ami_command("pjsip show endpoints", host, port, username, secret)
            endpoints = re.findall(r'Endpoint:\s+(\S+)', out)
            result_data["endpoints"] = endpoints
            result_data["raw_excerpt"] = out[:500]
            
        elif req.type == "pbx.registrations.list":
            out = await _run_ami_command("pjsip show registrations", host, port, username, secret)
            # Extrac <Registration/ServerURI......>  <Auth..........>  <Status.......>
            result_data["raw_excerpt"] = out[:500]
            
        elif req.type == "pbx.trunks.list":
            out = await _run_ami_command("pjsip show registrations", host, port, username, secret)
            result_data["raw_excerpt"] = out[:500]
            
        elif req.type == "pbx.dialplan.contexts":
            prefix = req.payload.get("context_prefix")
            if not prefix:
                return AgentTaskResponse(ok=False, error=AgentTaskError(code="context_required", message="context_prefix required for dialplan show"))
            out = await _run_ami_command(f"dialplan show {prefix}", host, port, username, secret)
            result_data["raw_excerpt"] = out[:1000]
            
        elif req.type == "pbx.snapshot.inventory":
            channels_out = await _run_ami_command("core show channels concise", host, port, username, secret)
            act_channels = len([l for l in channels_out.split('\n') if '!' in l])
            
            uptime_out = await _run_ami_command("core show uptime", host, port, username, secret)
            
            endpoints_out = await _run_ami_command("pjsip show endpoints", host, port, username, secret)
            endpoints = re.findall(r'Endpoint:\s+([^\s/]+)', endpoints_out)
            
            result_data["status"] = "snapshot_taken"
            result_data["active_channels"] = act_channels
            result_data["total_endpoints"] = len(endpoints)
            
            # Generate ProposedWrites
            # 1. PBX Target Update
            import datetime
            iso_now = datetime.datetime.utcnow().isoformat()
            
            pw_pbx = ProposedWrite(
                entity_kind="pbx",
                external_ref=target_id,
                action="upsert",
                patch={
                    "name": target["name"],
                    "tags": target["tags"],
                    "uptime": uptime_out,
                    "active_channels_count": act_channels,
                    "last_seen_at": iso_now
                },
                idempotency_key=f"pbx-snapshot:{req.task_id}:{target_id}"
            )
            proposed_writes.append(pw_pbx)
            
            # 2. Endpoints Update
            for ep in endpoints:
                pw_ep = ProposedWrite(
                    entity_kind="pbx_endpoint",
                    external_ref=f"{target_id}:{ep}",
                    action="upsert",
                    patch={
                        "pbx_target_id": target_id,
                        "endpoint_name": ep,
                        "status": "active" # For simplicity in V1
                    },
                    idempotency_key=f"pbx-snapshot:{req.task_id}:{target_id}:{ep}"
                )
                proposed_writes.append(pw_ep)
                
        else:
            return AgentTaskResponse(ok=False, error=AgentTaskError(code="unknown_task", message=f"Task type {req.type} not supported by PBX Agent"))

        return AgentTaskResponse(
            ok=True,
            result=result_data,
            proposed_writes=proposed_writes if proposed_writes else None
        )
    except Exception as e:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="ami_error", message=str(e)))


@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(req: AgentTaskRequest, request: Request):
    return await handle_agent_execute(req, request, _execute_handler)

@app.get("/capabilities")
async def get_capabilities():
    return {
        "capabilities": [
            "pbx.status",
            "pbx.channels.active",
            "pbx.endpoints.list",
            "pbx.registrations.list",
            "pbx.trunks.list",
            "pbx.dialplan.contexts",
            "pbx.snapshot.inventory"
        ],
        "version": "1.0.0"
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
