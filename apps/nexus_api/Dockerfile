FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

# Copy the dependency definitions
COPY pyproject.toml .

# Install dependencies into system environment
RUN uv pip install --system -r pyproject.toml

# Copy the applications and packages
COPY ./packages /app/packages
COPY ./apps /app/apps
COPY ./migrations /app/migrations
COPY ./alembic.ini /app/alembic.ini
COPY ./scripts /app/scripts

# Set python path so packages can be resolved
ENV PYTHONPATH=/app

CMD ["uvicorn", "apps.nexus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
