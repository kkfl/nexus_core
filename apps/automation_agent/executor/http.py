from typing import Any

import httpx
import structlog

from apps.automation_agent.client.registry import resolve_agent
from apps.automation_agent.client.secrets import fetch_secret

logger = structlog.get_logger(__name__)


async def execute_agent_action(
    agent_name: str,
    action: str,
    input_data: dict[str, Any],
    tenant_id: str,
    env: str,
    correlation_id: str,
    timeout_seconds: int = 30,
) -> tuple[bool, Any]:
    """
    Executes a specific action against another Nexus agent.
    Returns (success_boolean, parsed_response_or_error_string)
    """
    try:
        # 1. Resolve agent
        agent = await resolve_agent(agent_name, tenant_id, env)
    except Exception as e:
        logger.error("agent_resolution_failed_execution", agent_name=agent_name, error=str(e))
        return False, f"Resolution failed: {e}"

    # Parse action (e.g. "POST /v1/records")
    parts = action.strip().split(" ", 1)
    if len(parts) != 2:
        return False, f"Invalid action format '{action}'. Expected 'METHOD /path'"

    method, path = parts[0].upper(), parts[1]
    url = f"{agent.base_url}{path if path.startswith('/') else '/' + path}"

    headers = {
        "X-Service-ID": "automation-agent",
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }

    # 2. Handle Auth
    if agent.auth_scheme == "headers":
        if not agent.auth_secret_alias:
            return (
                False,
                f"Agent {agent_name} requires header auth but no secret alias is registered in registry.",
            )

        secret_val = await fetch_secret(agent.auth_secret_alias, tenant_id, env, correlation_id)
        if not secret_val:
            return (
                False,
                f"Failed to retrieve auth secret '{agent.auth_secret_alias}' from secrets-agent.",
            )

        headers["X-Agent-Key"] = str(secret_val)
    else:
        # V1 MVP supports X-Agent-Key headers.
        return False, f"Unsupported auth scheme '{agent.auth_scheme}' for agent {agent_name}"

    # 3. Execute HTTP
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            request_kwargs = {"headers": headers}
            if method in ("POST", "PUT", "PATCH"):
                request_kwargs["json"] = input_data
            elif method == "GET":
                request_kwargs["params"] = input_data

            resp = await client.request(method, url, **request_kwargs)

            try:
                resp_data = resp.json()
            except Exception:
                resp_data = resp.text

            if resp.is_error:
                logger.warning(
                    "agent_action_failed",
                    agent=agent_name,
                    status=resp.status_code,
                    response=str(resp_data)[:200],
                )
                return False, resp_data

            return True, resp_data

    except httpx.TimeoutException:
        logger.warning("agent_action_timeout", agent=agent_name, timeout=timeout_seconds)
        return False, "Agent request timed out"
    except Exception as e:
        logger.warning("agent_action_exception", agent=agent_name, error=str(e))
        return False, str(e)
