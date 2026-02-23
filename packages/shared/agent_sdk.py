import traceback
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request

from packages.shared.schemas.agent_sdk import AgentTaskError, AgentTaskRequest, AgentTaskResponse


async def handle_agent_execute(
    req: AgentTaskRequest,
    fastapi_request: Request,
    handler_func: Callable[[AgentTaskRequest], Coroutine[Any, Any, AgentTaskResponse]],
) -> AgentTaskResponse:
    """
    Standardizes the /execute endpoint wrapper for any agent.
    - Validates headers if needed
    - Enforces basic error counting/catching
    """

    # Ideally, we would authenticate here, but for now we expect the agent app to wire a Depends()
    # for API key auth or we do it inside the endpoint.

    correlation_id = fastapi_request.headers.get("X-Correlation-Id")
    if correlation_id:
        # One might put this into contextvars
        pass

    try:
        response = await handler_func(req)
        return response
    except Exception as e:
        # Standardize unhandled exceptions into an AgentTaskResponse
        stack_trace = traceback.format_exc()
        print(f"Unhandled error in agent execute: {stack_trace}")
        return AgentTaskResponse(
            ok=False,
            error=AgentTaskError(
                code="internal_agent_error", message=str(e), details={"traceback": stack_trace}
            ),
        )
