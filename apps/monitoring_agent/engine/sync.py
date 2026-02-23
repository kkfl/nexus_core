"""
Sync Engine - Pulls deployments from agent_registry and updates monitoring_targets
"""

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.monitoring_agent.config import get_settings
from apps.monitoring_agent.store.postgres import log_audit, upsert_target

logger = structlog.get_logger(__name__)
settings = get_settings()


async def sync_from_registry(db: AsyncSession, correlation_id: str):
    headers = {
        "X-Service-ID": "monitoring-agent",
        "X-Agent-Key": settings.nexus_registry_agent_key,
        "X-Correlation-ID": correlation_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.registry_base_url}/v1/deployments", headers=headers)
            if resp.status_code != 200:
                logger.error("registry_sync_failed", status=resp.status_code, body=resp.text)
                await log_audit(
                    db,
                    correlation_id,
                    "monitoring-agent",
                    None,
                    "prod",
                    "sync_registry",
                    "failed",
                    detail=f"HTTP {resp.status_code}",
                )
                return 0

            deployments = resp.json()
            synced_count = 0

            for d in deployments:
                target_dict = {
                    "id": d["id"],
                    "tenant_id": d.get("tenant_id"),
                    "env": d.get("env", "prod"),
                    "agent_name": d.get(
                        "agent_name", "unknown"
                    ),  # Technically registry GET /deployments returns agent_id, but the V1 schema joins them.
                    # Wait, let's parse the actual API output from registry_deployments.
                    # The registry /v1/deployments endpoint does not return `agent_name` by default unless expanded.
                    # Wait! In Nexus V1, deployments typically have agent_id. We must fetch the agent separately if name isn't returned, or fetch /v1/agents.
                    # Let's hit /v1/agents to map names, or just assume the agent_registry GET /v1/agents handles this.
                }

                # ... Let's make sure we map agent names ...
                # First let's fetch all agents:
            agents_resp = await client.get(
                f"{settings.registry_base_url}/v1/agents", headers=headers
            )
            agents = (
                {a["id"]: a["name"] for a in agents_resp.json()}
                if agents_resp.status_code == 200
                else {}
            )

            for d in deployments:
                a_name = agents.get(d["agent_id"], "unknown-agent")
                if a_name == "monitoring-agent":
                    # Skip monitoring itself to avoid noise, or keep it to self-monitor.
                    pass

                target_dict = {
                    "id": d["id"],
                    "tenant_id": d.get("tenant_id"),
                    "env": d.get("env", "prod"),
                    "agent_name": a_name,
                    "deployment_id": d["id"],
                    "base_url": d["base_url"],
                    "tags": [],
                }
                await upsert_target(db, target_dict)
                synced_count += 1

            await log_audit(
                db,
                correlation_id,
                "monitoring-agent",
                None,
                "prod",
                "sync_registry",
                "success",
                detail=f"Synced {synced_count} deployments",
            )
            await db.commit()
            return synced_count

    except Exception as e:
        logger.error("registry_sync_exception", error=str(e))
        await log_audit(
            db,
            correlation_id,
            "monitoring-agent",
            None,
            "prod",
            "sync_registry",
            "error",
            detail=str(e),
        )
        return 0
