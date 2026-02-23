"""
Checker Engine - Executes concurrent health/ready checks against monitored deployments.
"""
import asyncio
import httpx
import structlog
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from apps.monitoring_agent.store.postgres import MonitoringTarget, MonitoringCheck, get_target_state, record_check, get_targets
from apps.monitoring_agent.engine.alerter import evaluate_and_alert
from apps.monitoring_agent.config import get_settings
from apps.monitoring_agent import metrics

logger = structlog.get_logger(__name__)
settings = get_settings()

async def run_checks(db: AsyncSession, tenant_id: str = None, env: str = None, correlation_id: str = None):
    targets = await get_targets(db, tenant_id, env)
    if not targets:
        logger.info("no_targets_found_for_checks")
        return {"total": 0, "success": 0, "failed": 0}

    results_data = []
    
    # 1. Concurrent HTTP Checks
    sem = asyncio.Semaphore(20)
    
    async def _safe_http_check(target: MonitoringTarget):
        async with sem:
            # We just do the HTTP check part here without DB
            return await _execute_http_check(target, correlation_id)

    http_results = await asyncio.gather(*[_safe_http_check(t) for t in targets])
    
    # 2. Sequential DB Writes
    successes = 0
    for target, result in zip(targets, http_results):
        is_ok = await _process_check_result(db, target, correlation_id, result)
        if is_ok:
            successes += 1
            
    await db.commit()
    return {"total": len(targets), "success": successes, "failed": len(targets) - successes}


async def _execute_http_check(target: MonitoringTarget, correlation_id: str) -> tuple:
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    metrics.inc("monitoring_checks_total", agent=target.agent_name)
    
    health_ok = False
    ready_ok = False
    health_status = None
    ready_status = None
    capabilities_hash = None
    error_code = None
    error_detail = None
    
    headers = {
        "X-Service-ID": "monitoring-agent",
        "X-Correlation-ID": correlation_id or str(uuid.uuid4())
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # 1. Check healthz
            resp_h = await client.get(f"{target.base_url}/healthz", headers=headers)
            health_status = resp_h.status_code
            if health_status == 200:
                health_ok = True
            else:
                error_code = "healthz_failed"
                error_detail = f"HTTP {health_status}"

            # 2. Check readyz
            resp_r = await client.get(f"{target.base_url}/readyz", headers=headers)
            ready_status = resp_r.status_code
            if ready_status == 200:
                ready_ok = True
            elif not error_code:
                error_code = "readyz_failed"
                error_detail = f"HTTP {ready_status}"

            # 3. Check capabilities (optional, don't fail if 404)
            resp_c = await client.get(f"{target.base_url}/capabilities", headers=headers)
            if resp_c.status_code == 200:
                import hashlib
                import json
                try:
                    cap_data = resp_c.json()
                    capabilities_hash = hashlib.sha256(json.dumps(cap_data, sort_keys=True).encode()).hexdigest()
                except Exception:
                    pass

        except httpx.TimeoutException:
            error_code = "timeout"
            error_detail = "Request timed out after 5.0s"
        except httpx.RequestError as e:
            error_code = "connection_error"
            import re
            error_detail = re.sub(r'[A-Za-z0-9+/=]{32,}', '[REDACTED]', str(e))[:250]
        except Exception as e:
            error_code = "internal_error"
            error_detail = str(e)[:250]

    ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    latency_ms = int((ended_at - started_at).total_seconds() * 1000)
    return (health_ok, ready_ok, health_status, ready_status, capabilities_hash, error_code, error_detail, latency_ms, started_at, ended_at)

async def _process_check_result(db: AsyncSession, target: MonitoringTarget, correlation_id: str, result_data: tuple) -> bool:
    (health_ok, ready_ok, health_status, ready_status, capabilities_hash, error_code, error_detail, latency_ms, started_at, ended_at) = result_data
    
    # Create the check record
    check = MonitoringCheck(
        id=str(uuid.uuid4()),
        target_id=target.id,
        correlation_id=correlation_id,
        started_at=started_at,
        ended_at=ended_at,
        health_status_code=health_status,
        ready_status_code=ready_status,
        health_ok=health_ok,
        ready_ok=ready_ok,
        latency_ms=latency_ms,
        error_code=error_code,
        error_detail_redacted=error_detail,
        capabilities_hash=capabilities_hash
    )
    db.add(check) # Safe to add sequentially within caller loop
    
    # Evaluate state and alert
    state = await get_target_state(db, target.id)
    if not state:
        logger.warning("target_missing_state_record", target_id=target.id)
        from apps.monitoring_agent.store.postgres import MonitoringState
        state = MonitoringState(target_id=target.id, current_state="UP", consecutive_failures=0)
        db.add(state)
        
    is_ok = health_ok and ready_ok
    await evaluate_and_alert(db, target, state, correlation_id, is_ok, error_detail, capabilities_hash)
    
    # Metrics
    metrics.set_gauge("monitoring_latency_ms", latency_ms, agent=target.agent_name)
    metrics.set_gauge("monitoring_state", 1 if is_ok else 0, agent=target.agent_name)
    if not is_ok:
        metrics.inc("monitoring_failures_total", agent=target.agent_name, reason=error_code or "unknown")
        
    return is_ok
