FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/agent_registry/requirements.txt apps/agent_registry/

RUN pip install --no-cache-dir -r apps/agent_registry/requirements.txt

COPY packages/shared packages/shared
COPY apps/agent_registry apps/agent_registry

EXPOSE 8012
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8012/healthz || exit 1

CMD ["uvicorn", "apps.agent_registry.main:app", "--host", "0.0.0.0", "--port", "8012"]
