FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/pbx_agent /app/apps/pbx_agent

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic-settings \
    sqlalchemy \
    asyncpg \
    httpx \
    structlog

ENV PYTHONPATH=/app
ENV PORT=8011

EXPOSE 8011

CMD ["sh", "-c", "uvicorn apps.pbx_agent.main:app --host 0.0.0.0 --port 8011"]
