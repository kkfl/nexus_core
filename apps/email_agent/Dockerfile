FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/email_agent /app/apps/email_agent
COPY apps/notifications_agent /app/apps/notifications_agent

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic-settings \
    sqlalchemy \
    asyncpg \
    httpx \
    structlog \
    aiosmtplib \
    paramiko \
    redis>=5.0.0

ENV PYTHONPATH=/app
ENV PORT=8014

EXPOSE 8014

CMD ["sh", "-c", "uvicorn apps.email_agent.main:app --host 0.0.0.0 --port 8014"]
