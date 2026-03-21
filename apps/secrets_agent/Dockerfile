FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    sqlalchemy[asyncio]==2.0.36 \
    asyncpg==0.30.0 \
    pydantic==2.9.2 \
    pydantic-settings==2.5.2 \
    "pydantic[email]" \
    httpx==0.27.2 \
    cryptography==43.0.3 \
    structlog==24.4.0 \
    alembic==1.13.3 \
    python-multipart==0.0.12

# Copy application code
COPY ./apps/secrets_agent /app/apps/secrets_agent
COPY ./apps/notifications_agent /app/apps/notifications_agent
COPY ./packages /app/packages

EXPOSE 8007

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8007/healthz || exit 1

CMD ["uvicorn", "apps.secrets_agent.main:app", "--host", "0.0.0.0", "--port", "8007"]
