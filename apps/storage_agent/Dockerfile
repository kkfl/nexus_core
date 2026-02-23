FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY packages/shared /app/packages/shared
COPY apps/storage_agent /app/apps/storage_agent
COPY apps/secrets_agent /app/apps/secrets_agent

RUN pip install --no-cache-dir fastapi uvicorn "pydantic[email]" pydantic-settings httpx structlog aioboto3 boto3 cryptography sqlalchemy asyncpg alembic prometheus-client python-multipart

ENV PYTHONPATH=/app
ENV PORT=8005

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn apps.storage_agent.main:app --host 0.0.0.0 --port ${PORT}"]
