FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/notifications_agent /app/apps/notifications_agent
COPY apps/secrets_agent /app/apps/secrets_agent

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    "pydantic[email]" \
    pydantic-settings \
    httpx \
    structlog \
    cryptography \
    sqlalchemy[asyncio] \
    asyncpg \
    aiosmtplib

ENV PYTHONPATH=/app
ENV PORT=8008

EXPOSE ${PORT}

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/healthz')"

CMD ["sh", "-c", "uvicorn apps.notifications_agent.main:app --host 0.0.0.0 --port ${PORT}"]
