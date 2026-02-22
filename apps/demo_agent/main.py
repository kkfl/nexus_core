from fastapi import FastAPI, Request
from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="Demo Agent V1 (SDK)")

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    print(f"Demo Agent received task {req.task_id} of type {req.type}")
    
    if req.type == "echo":
        persona_received = None
        if req.persona:
            persona_received = {
                "name": req.persona.name,
                "version": req.persona.version
            }
        ctx_len = len(req.context) if req.context else 0
        return AgentTaskResponse(
            ok=True,
            result={
                "echo": req.payload,
                "persona_received": persona_received,
                "context_received_count": ctx_len,
                "context": req.context
            }
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
    return {"capabilities": ["echo"], "version": "1.0.0"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
