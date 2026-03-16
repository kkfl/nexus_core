"""
Shared heartbeat background task for Nexus agents.

Usage (in agent lifespan):

    from packages.shared.heartbeat import start_heartbeat, stop_heartbeat

    @asynccontextmanager
    async def lifespan(app):
        start_heartbeat("dns-agent")
        yield
        await stop_heartbeat()
"""

from __future__ import annotations

import asyncio
import contextlib
import os

import structlog

logger = structlog.get_logger(__name__)

_task: asyncio.Task | None = None
_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))  # seconds


async def _heartbeat_loop(agent_name: str) -> None:
    """Post heartbeat to agent registry in a loop."""
    import httpx

    registry_url = os.environ.get(
        "AGENT_REGISTRY_URL", os.environ.get("REGISTRY_BASE_URL", "http://agent-registry:8012")
    )
    service_id = os.environ.get("REGISTRY_SERVICE_ID", "nexus")
    agent_key = os.environ.get("NEXUS_REGISTRY_AGENT_KEY", "nexus-registry-key")

    url = f"{registry_url}/v1/agents/{agent_name}/heartbeat"
    headers = {"X-Service-ID": service_id, "X-Agent-Key": agent_key}

    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers)
                if resp.status_code == 204:
                    logger.debug("heartbeat_sent", agent=agent_name)
                else:
                    logger.warning(
                        "heartbeat_failed",
                        agent=agent_name,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
        except Exception as exc:
            logger.warning("heartbeat_error", agent=agent_name, error=str(exc)[:200])

        await asyncio.sleep(_INTERVAL)


def start_heartbeat(agent_name: str) -> None:
    """Start the heartbeat background task."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_heartbeat_loop(agent_name))
        logger.info("heartbeat_started", agent=agent_name, interval=_INTERVAL)


async def stop_heartbeat() -> None:
    """Cancel the heartbeat background task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        logger.info("heartbeat_stopped")
    _task = None
