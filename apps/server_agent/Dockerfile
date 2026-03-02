FROM python:3.12-slim

WORKDIR /app

COPY apps/server_agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/ /app/packages/
COPY apps/server_agent/ /app/apps/server_agent/

ENV PYTHONPATH=/app
EXPOSE 8010

CMD ["uvicorn", "apps.server_agent.main:app", "--host", "0.0.0.0", "--port", "8010"]
