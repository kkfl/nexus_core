import os
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.nexus_api.metrics import get_metrics_response, metrics_middleware
from apps.nexus_api.routers import (
    agents,
    artifacts,
    audit,
    auth,
    backup,
    brain_routes,
    carrier,
    docs,
    email_events,
    entities,
    events,
    internal,
    ip_allowlist,
    kb,
    monitoring,
    pbx,
    persona_defaults,
    personas,
    portal_secrets,
    secrets,
    storage,
    task_routes,
    tasks,
    users,
)

logger = structlog.get_logger()

# Docs disabled unless explicitly enabled
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").lower() == "true"
docs_kwargs = {} if ENABLE_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}

import asyncio
from contextlib import asynccontextmanager

import httpx

from packages.shared.client.agent_registry import get_registry_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed the Agent Registry with native Nexus agents on startup
    client = get_registry_client()
    agents_to_register = [
        {"name": "secrets-agent", "url": "http://secrets-agent:8007", "auth": "headers"},
        {
            "name": "dns-agent",
            "url": "http://dns-agent:8006",
            "auth": "headers",
            "auth_secret_alias": "dns-agent.automation-agent.key",
        },
        {
            "name": "notifications-agent",
            "url": "http://notifications-agent:8008",
            "auth": "headers",
            "auth_secret_alias": "notifications-agent.automation-agent.key",
        },
        {
            "name": "carrier-agent",
            "url": "http://carrier-agent:8009",
            "auth": "headers",
            "auth_secret_alias": "carrier-agent.automation-agent.key",
        },
        {
            "name": "storage-agent",
            "url": "http://storage-agent:8005",
            "auth": "headers",
            "auth_secret_alias": "storage-agent.automation-agent.key",
        },
        {
            "name": "pbx-agent",
            "url": "http://pbx-agent:8011",
            "auth": "headers",
            "auth_secret_alias": "pbx-agent.automation-agent.key",
        },
        {
            "name": "monitoring-agent",
            "url": "http://monitoring-agent:8004",
            "auth": "headers",
            "auth_secret_alias": "monitoring-agent.automation-agent.key",
        },
        {"name": "automation-agent", "url": "http://automation-agent:8013", "auth": "headers"},
    ]

    # Wait for agent-registry to be ready (up to 10 seconds)
    registry_up = False
    for _ in range(5):
        try:
            async with httpx.AsyncClient(timeout=1.0) as hc:
                await hc.get(f"{client.registry_base_url}/healthz")
            registry_up = True
            break
        except Exception:
            await asyncio.sleep(2)

    if registry_up:
        try:
            async with httpx.AsyncClient(timeout=5.0) as hc:
                for a in agents_to_register:
                    # 1. Create agent (409 Conflict is expected if already exists)
                    await hc.post(
                        f"{client.registry_base_url}/v1/agents",
                        headers=client.headers,
                        json={"name": a["name"]},
                    )

                    # Fetch agent_id to attach the deployment
                    agent_resp = await hc.get(
                        f"{client.registry_base_url}/v1/agents/{a['name']}", headers=client.headers
                    )
                    if agent_resp.status_code == 200:
                        agent_id = agent_resp.json()["id"]

                        # 2. Check if deployment already exists for this agent+env
                        existing_resp = await hc.get(
                            f"{client.registry_base_url}/v1/deployments",
                            headers=client.headers,
                            params={"agent_id": agent_id, "env": "prod"},
                        )
                        existing_deps = (
                            existing_resp.json() if existing_resp.status_code == 200 else []
                        )

                        if existing_deps:
                            logger.debug(
                                "agent_deployment_exists", agent=a["name"], count=len(existing_deps)
                            )
                        else:
                            # Only create if no deployment exists yet
                            await hc.post(
                                f"{client.registry_base_url}/v1/deployments",
                                headers=client.headers,
                                json={
                                    "agent_id": agent_id,
                                    "env": "prod",
                                    "base_url": a["url"],
                                    "auth_scheme": a["auth"],
                                    "auth_secret_alias": a.get("auth_secret_alias"),
                                },
                            )
            logger.info("agent_registry_seeded", agents_count=len(agents_to_register))
        except Exception as exc:
            logger.error("agent_registry_seeding_failed", error=str(exc))
    else:
        logger.warning("agent_registry_unreachable_during_startup")

    # ── Start heartbeat ────────────────────────────────────────────
    from packages.shared.heartbeat import start_heartbeat

    start_heartbeat("nexus_api")

    # ── Start stale-heartbeat monitor ──────────────────────────────
    async def _heartbeat_monitor():
        """Every 2 min, check for agents that missed heartbeats and send Telegram alert."""
        from datetime import UTC, datetime, timedelta

        import httpx

        from packages.shared.alerts import send_alert

        _alerted: set[str] = set()  # track which agents we already alerted on
        _tick_count = 0  # track cycles for periodic OK log

        while True:
            await asyncio.sleep(120)  # check every 2 min
            _tick_count += 1
            try:
                async with httpx.AsyncClient(timeout=5) as hc:
                    resp = await hc.get(
                        f"{client.registry_base_url}/v1/agents",
                        headers=client.headers,
                    )
                    if resp.status_code != 200:
                        continue
                    agents_list = resp.json()

                now = datetime.now(UTC)
                threshold = now - timedelta(minutes=3)
                healthy_count = 0

                for a in agents_list:
                    name = a.get("name", "")
                    hb = a.get("last_heartbeat")

                    if hb is None:
                        continue  # never checked in yet, skip

                    from dateutil.parser import isoparse

                    hb_time = isoparse(hb)
                    if hb_time.tzinfo is None:
                        hb_time = hb_time.replace(tzinfo=UTC)

                    if hb_time < threshold:
                        if name not in _alerted:
                            _alerted.add(name)
                            send_alert(
                                "agent_heartbeat_stale",
                                "system",
                                f"Agent '{name}' — last heartbeat: {hb}",
                                severity="warn",
                            )
                            logger.warning("agent_heartbeat_stale", agent=name, last_heartbeat=hb)

                            # Telegram alert
                            from apps.nexus_api.notify import notify_action

                            await notify_action(
                                action="agent.down",
                                subject="\U0001f6a8 Agent DOWN",
                                body=f"{name} — last seen: {hb}",
                                event_type="nexus.agent.down",
                                severity="critical",
                                actor_type="system",
                                actor_id="heartbeat-monitor",
                                payload={"agent": name, "last_heartbeat": hb},
                            )
                    else:
                        healthy_count += 1
                        if name in _alerted:
                            _alerted.discard(name)
                            # Recovery notification
                            from apps.nexus_api.notify import notify_action

                            await notify_action(
                                action="agent.recovered",
                                subject="\u2705 Agent Recovered",
                                body=f"{name} is back online",
                                event_type="nexus.agent.recovered",
                                severity="info",
                                actor_type="system",
                                actor_id="heartbeat-monitor",
                                payload={"agent": name},
                            )

                # Every 15 cycles (~30 min), log a heartbeat-OK to the activity log
                if _tick_count % 15 == 0:
                    try:
                        from packages.shared.db import AsyncSessionLocal
                        from packages.shared.events.schema import EventActor, NexusEvent
                        from packages.shared.events.store import persist_event

                        event = NexusEvent(
                            event_type="nexus.heartbeat.ok",
                            produced_by="nexus-api",
                            correlation_id="",
                            actor=EventActor(type="system", id="heartbeat-monitor"),
                            tenant_id="nexus",
                            severity="info",
                            payload={
                                "summary": f"\U0001f49a Heartbeat OK — {healthy_count}/{len(agents_list)} agents healthy",
                                "detail": "All monitored agents responding normally",
                            },
                        )
                        async with AsyncSessionLocal() as db:
                            await persist_event(db, event)
                            await db.commit()
                    except Exception:
                        pass  # non-critical

            except Exception as exc:
                logger.debug("heartbeat_monitor_error", error=str(exc)[:200])

    _monitor_task = asyncio.create_task(_heartbeat_monitor())

    yield

    _monitor_task.cancel()
    from packages.shared.heartbeat import stop_heartbeat

    await stop_heartbeat()


app = FastAPI(
    title="Nexus Core API",
    version="1.0.0",
    description="Nexus Core orchestrator and persona registry.",
    redirect_slashes=False,
    lifespan=lifespan,
    **docs_kwargs,
)

# CORS origins
cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if not cors_origins:
    cors_origins = []

from starlette.middleware.base import BaseHTTPMiddleware

app.add_middleware(BaseHTTPMiddleware, dispatch=metrics_middleware)

# CORS must be last added (outermost) so it handles OPTIONS preflight before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id

    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
    )

    # ── IP Allowlist Enforcement ──────────────────────────────────
    # Bypass CORS preflight (OPTIONS) and health endpoints
    bypass_paths = ("/healthz", "/readyz", "/metrics")
    skip_ip_check = request.method == "OPTIONS" or request.url.path.startswith(bypass_paths)
    if not skip_ip_check:
        try:
            import ipaddress as _ipaddress

            from sqlalchemy.future import select as sa_select

            from packages.shared.db import AsyncSessionLocal
            from packages.shared.models import IpAllowlistEntry

            async with AsyncSessionLocal() as ip_db:
                ip_res = await ip_db.execute(
                    sa_select(IpAllowlistEntry).where(IpAllowlistEntry.is_active.is_(True))
                )
                allowlist = ip_res.scalars().all()

            # Fail-open: if no entries exist, all IPs are allowed
            if allowlist:
                client_ip = request.client.host if request.client else "0.0.0.0"
                allowed = any(
                    _ipaddress.ip_address(client_ip)
                    in _ipaddress.ip_network(entry.cidr, strict=False)
                    for entry in allowlist
                )
                if not allowed:
                    from starlette.responses import JSONResponse

                    logger.warning("ip_blocked", client_ip=client_ip)
                    # Must include CORS headers so the browser can read the 403
                    origin = request.headers.get("origin", "")
                    resp_headers = {}
                    if origin and origin in cors_origins:
                        resp_headers["Access-Control-Allow-Origin"] = origin
                        resp_headers["Access-Control-Allow-Credentials"] = "true"
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"IP address {client_ip} not in allowlist"},
                        headers=resp_headers,
                    )
        except Exception as exc:
            # Don't block requests if the allowlist check itself fails
            logger.error("ip_allowlist_check_error", error=str(exc))

    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id

    # ── Security Headers ──────────────────────────────────────────
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    if ENABLE_DOCS:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:;"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'self';"

    return response


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(personas.router, prefix="/personas", tags=["personas"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])
app.include_router(task_routes.router, prefix="/task-routes", tags=["task-routes"])
app.include_router(persona_defaults.router, prefix="/persona-defaults", tags=["persona-defaults"])
app.include_router(kb.router, prefix="/kb", tags=["kb"])
app.include_router(secrets.router, prefix="/secrets", tags=["secrets"])
app.include_router(portal_secrets.router, prefix="/portal/secrets", tags=["portal-secrets"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(entities.router, prefix="/entities", tags=["entities"])
app.include_router(pbx.router, prefix="/pbx", tags=["pbx"])
app.include_router(internal.router, prefix="/internal", tags=["internal"])
app.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
app.include_router(storage.router, prefix="/storage", tags=["storage"])
app.include_router(carrier.router, prefix="/carrier", tags=["carrier"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])
app.include_router(brain_routes.router, prefix="/brain", tags=["brain"])
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(ip_allowlist.router, prefix="/settings/ip-allowlist", tags=["settings"])
app.include_router(email_events.router, prefix="/notify", tags=["notifications"])
app.include_router(backup.router, prefix="/settings/backup", tags=["settings"])


@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
async def readyz():
    return {"status": "ready"}


@app.get("/metrics", tags=["metrics"])
async def metrics():
    return get_metrics_response()


@app.get("/api/version", tags=["system"])
async def get_version():
    version_str = "unknown"
    version_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION"
    )
    if os.path.exists(version_file):
        with open(version_file) as f:
            version_str = f.read().strip()
    return {
        "version": version_str,
        "commit": os.environ.get("GIT_COMMIT", "unknown"),
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
    }
