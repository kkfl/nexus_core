FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /app/packages/shared
COPY apps/carrier_agent /app/apps/carrier_agent

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx structlog

ENV PYTHONPATH=/app
ENV PORT=8006

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn apps.carrier_agent.main:app --host 0.0.0.0 --port ${PORT}"]
