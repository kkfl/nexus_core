from typing import Any

from fastapi import HTTPException


def enforce_persona_policy(
    task_type: str,
    required_capabilities: list[str],
    agent_timeout_seconds: int | None,
    tools_policy: dict[str, Any],
) -> dict:
    """
    Validates a task dispatch against a persona's tools_policy.
    Returns a dictionary of potentially clamped configuration (e.g., timeout_seconds),
    or raises HTTPException with specific detail codes if policy violates.
    """
    if not tools_policy:
        return {"timeout_seconds": agent_timeout_seconds}

    # 1. Check deny list FIRST
    deny_task_types = tools_policy.get("deny_task_types", [])
    if task_type in deny_task_types:
        raise HTTPException(status_code=403, detail="persona_task_type_denied")

    # 2. Check allow list NEXT
    allow_task_types = tools_policy.get("allow_task_types")  # None means allow all if not denied
    if allow_task_types is not None and task_type not in allow_task_types:
        raise HTTPException(status_code=403, detail="persona_task_type_denied")

    # 3. Check capabilities
    allowed_capabilities = tools_policy.get("allowed_capabilities", [])
    if required_capabilities and not all(c in allowed_capabilities for c in required_capabilities):
        raise HTTPException(status_code=403, detail="persona_capabilities_denied")

    # 4. Clamp timeout
    max_timeout = tools_policy.get("max_timeout_seconds")
    final_timeout = agent_timeout_seconds
    if max_timeout is not None and (final_timeout is None or final_timeout > max_timeout):
        final_timeout = max_timeout

    return {"timeout_seconds": final_timeout}
