"""
Alerter Engine - evaluates state transitions and dispatches to notifications_agent
"""
import httpx
import structlog
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from apps.monitoring_agent.store.postgres import MonitoringState, MonitoringTarget, log_audit
from apps.monitoring_agent.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

COOLDOWN_MINUTES = 15

async def evaluate_and_alert(
    db: AsyncSession,
    target: MonitoringTarget,
    state: MonitoringState,
    correlation_id: str,
    check_ok: bool,
    error_detail: str,
    capabilities_hash: str
):
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    previous_state = state.current_state

    # 1. Update basic state
    state.last_seen_at = now_dt
    
    if check_ok:
        new_state = "UP"
        state.consecutive_failures = 0
    else:
        state.consecutive_failures += 1
        new_state = "DOWN" if state.consecutive_failures >= 3 else "DEGRADED"

    state_changed = (new_state != previous_state)
    if state_changed:
        state.last_state_change_at = now_dt
        state.current_state = new_state
        await log_audit(db, correlation_id, "monitoring-agent", target.tenant_id, target.env, "state_change", new_state, target.id, f"{previous_state} -> {new_state}")

    # 2. Determine if Alert Required
    alert_required = False
    severity = "info"
    alert_reason = ""

    # Always alert on UP -> DOWN/DEGRADED boundary or DOWN -> UP recovery
    if state_changed:
        alert_required = True
        if new_state == "DOWN":
            severity = "critical"
            alert_reason = f"Target {target.agent_name} is DOWN. Error: {error_detail}"
        elif new_state == "DEGRADED":
            severity = "error"
            alert_reason = f"Target {target.agent_name} is DEGRADED. Error: {error_detail}"
        elif new_state == "UP":
            severity = "info"
            alert_reason = f"Target {target.agent_name} has RECOVERED and is now UP."
    # If it stays DOWN, alert periodically if cooldown expired
    elif new_state == "DOWN":
        if not state.alert_cooldown_until or now_dt >= state.alert_cooldown_until:
            alert_required = True
            severity = "critical"
            alert_reason = f"Target {target.agent_name} is STILL DOWN. Error: {error_detail}"

    # 3. Dispatch Alert
    if alert_required:
        await dispatch_alert(target, severity, alert_reason, correlation_id)
        state.last_alerted_at = now_dt
        # Set cooldown only for negative states
        if new_state in ("DOWN", "DEGRADED"):
            state.alert_cooldown_until = now_dt + timedelta(minutes=COOLDOWN_MINUTES)
        else:
            state.alert_cooldown_until = None
            
        await log_audit(db, correlation_id, "monitoring-agent", target.tenant_id, target.env, "alert_dispatched", "success", target.id, alert_reason)

    await db.flush()

async def dispatch_alert(target: MonitoringTarget, severity: str, message: str, correlation_id: str):
    import json
    # Use generic notification to telegram
    payload = {
        "tenant_id": target.tenant_id or "nexus",
        "env": target.env,
        "channels": ["telegram"],
        "severity": severity,
        "body": f"[MONITORING] {message}\nAgent: {target.agent_name}\nURL: {target.base_url}\nEnv: {target.env}\nTenant: {target.tenant_id}",
        "idempotency_key": f"monitor-alert-{target.id}-{int(datetime.now().timestamp())}",
        "correlation_id": correlation_id
    }
    
    headers = {
        "X-Service-ID": "monitoring-agent",
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json"
    }

    try:
        # In a real deployed V1, monitoring_agent would fetch a token for notifications_agent.
        # But notifications_agent accepts the automation-agent key or its own key depending on policy.
        # We'll use a hardcoded local passthrough or fetch secret if needed. For V1 we fetch from Secrets Agent
        from apps.monitoring_agent.engine.secrets import get_secret
        # Lookup the monitoring-agent deployment auth secret
        alias = "monitoring-agent.automation-agent.key" # The established system secret for notifying
        token = await get_secret(alias, target.tenant_id or "nexus", target.env, correlation_id)
        if token:
            headers["X-Agent-Key"] = token
            
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{settings.notifications_base_url}/v1/notify", json=payload, headers=headers, timeout=5.0)
            if resp.status_code >= 400:
                logger.error("failed_to_dispatch_alert", status_code=resp.status_code, body=resp.text)
            else:
                logger.info("alert_dispatched_successfully", target=target.agent_name, severity=severity)
    except Exception as e:
        logger.error("alert_dispatch_exception", error=str(e))
