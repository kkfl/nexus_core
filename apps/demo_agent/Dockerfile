FROM python:3.12-slim

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system fastapi uvicorn "pydantic[email]"

COPY ./apps/demo_agent /app/apps/demo_agent
COPY ./packages /app/packages
ENV PYTHONPATH=/app

CMD ["uvicorn", "apps.demo_agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
