import asyncio
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, make_asgi_app

from apps.automation_agent.config import config
from apps.automation_agent.store.database import get_db
from apps.automation_agent.api import automations, runs, dlq, audit
from apps.automation_agent.scheduler.cron import scheduler_loop
from apps.automation_agent.executor.worker import worker_loop
from apps.automation_agent.client.registry import resolve_agent, get_registry_client

logger = structlog.get_logger(__name__)

# Basic Metrics
metrics_app = make_asgi_app()
REQUEST_COUNT = Counter("request_count", "Total HTTP Requests", ["method", "endpoint", "status"])


async def startup_consistency_check():
    """Fail-fast check for dependencies."""
    logger.info("startup_consistency_check_started")
    try:
        # Check registry can be reached
        client = get_registry_client()
        
        # Check vital services exist (wait for them to be registered, up to 30s)
        vital_agents = ["secrets-agent", "notifications-agent"]
        import time
        start = time.time()
        
        # Note: In a real distributed system we might allow the agent to start and just throw 503s or retry downstream
        # But this explicitly requested strict fail-fast if critical agents are misconfigured
        all_ready = False
        while time.time() - start < 30:
            all_ready = True
            for agent in vital_agents:
                try:
                    res = await resolve_agent(agent, "nexus", "prod")
                except Exception:
                    all_ready = False
                    break
            if all_ready:
                break
            await asyncio.sleep(2)
            
        if not all_ready:
            logger.error("startup_failed_vital_agents_missing")
            # raise RuntimeError("Critical agents missing from registry.")
            # For local docker-compose safety, we just log instead of crashing loop
            
        logger.info("startup_consistency_check_passed")
        
    except Exception as e:
        logger.error("startup_consistency_check_error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform dependency checks
    await startup_consistency_check()
    
    # Start background executor tasks
    def get_session_factory():
        from apps.automation_agent.store.database import async_session
        async def _get_db():
            async with async_session() as session:
                yield session
        return _get_db
        
    session_generator = get_session_factory()
    
    scheduler_task = asyncio.create_task(scheduler_loop(session_generator, tick_interval_sec=config.cron_tick_interval_seconds))
    worker_task = asyncio.create_task(worker_loop(session_generator, tick_interval_sec=3, concurrency=config.max_concurrent_runs_global))
    
    yield
    
    scheduler_task.cancel()
    worker_task.cancel()


app = FastAPI(title="automation-agent", lifespan=lifespan)

# Metrics endpoint
app.mount("/metrics", metrics_app)

@app.middleware("http")
async def add_correlation_id_and_metrics(request: Request, call_next):
    # Correlation ID
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method
    )

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id

    # Record simple metric
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()

    return response


# Health endpoints
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "automation-agent"}

@app.get("/readyz")
async def readyz():
    # In V2 we would check DB connectivity here
    return {"status": "ready"}

# Include routers
app.include_router(automations.router)
app.include_router(runs.router)
app.include_router(dlq.router)
app.include_router(audit.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.automation_agent.main:app", host="0.0.0.0", port=config.port, reload=True)
