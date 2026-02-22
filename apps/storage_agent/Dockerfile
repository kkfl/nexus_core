FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/storage_agent /app/apps/storage_agent

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx structlog aioboto3 boto3

ENV PYTHONPATH=/app
ENV PORT=8005

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn apps.storage_agent.main:app --host 0.0.0.0 --port ${PORT}"]
