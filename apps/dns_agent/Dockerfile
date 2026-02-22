FROM python:3.12-slim

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system fastapi uvicorn pydantic

COPY ./apps/dns_agent /app/apps/dns_agent
COPY ./packages /app/packages
ENV PYTHONPATH=/app

CMD ["uvicorn", "apps.dns_agent.main:app", "--host", "0.0.0.0", "--port", "8002"]
