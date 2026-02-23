FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/carrier_agent /app/apps/carrier_agent
COPY apps/secrets_agent /app/apps/secrets_agent

RUN pip install --no-cache-dir fastapi uvicorn "pydantic[email]" pydantic-settings httpx structlog cryptography python-dotenv "sqlalchemy[asyncio]" asyncpg pgvector greenlet

ENV PYTHONPATH=/app
ENV PORT=8009

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn apps.carrier_agent.main:app --host 0.0.0.0 --port ${PORT}"]
