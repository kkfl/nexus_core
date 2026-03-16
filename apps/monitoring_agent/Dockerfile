FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/monitoring_agent /app/apps/monitoring_agent

RUN pip install --no-cache-dir fastapi uvicorn "pydantic[email]" pydantic-settings httpx structlog sqlalchemy asyncpg alembic asyncssh

ENV PYTHONPATH=/app
ENV PORT=8004

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn apps.monitoring_agent.main:app --host 0.0.0.0 --port ${PORT}"]
