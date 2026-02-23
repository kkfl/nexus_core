FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    sqlalchemy[asyncio]==2.0.36 \
    asyncpg==0.30.0 \
    pydantic==2.9.2 \
    pydantic-settings==2.5.2 \
    httpx==0.27.2 \
    cryptography==43.0.3 \
    structlog==24.4.0 \
    alembic==1.13.3 \
    prometheus-client \
    croniter \
    jinja2

# We need the shared packages too, so we copy the root pyproject and packages locally
# For a monorepo docker context, we assume docker build is run from nexus_core/
COPY packages/ ./packages/
COPY apps/automation_agent/ ./apps/automation_agent/

# Install the shared package explicitly if needed, or rely on PYTHONPATH
ENV PYTHONPATH=/app

CMD ["uvicorn", "apps.automation_agent.main:app", "--host", "0.0.0.0", "--port", "8013"]
