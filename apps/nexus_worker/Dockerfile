FROM python:3.12-slim

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system -r pyproject.toml

COPY ./packages /app/packages
COPY ./apps /app/apps
ENV PYTHONPATH=/app

CMD ["sh", "-c", "rq worker nexus_tasks --url $REDIS_URL"]
