FROM python:3.11-slim

WORKDIR /app

COPY apps/control-plane/pyproject.toml ./
COPY apps/control-plane/app/ ./app/
COPY packages/ ./packages/
COPY apps/sandbox-executor/ ./apps/sandbox-executor/
RUN pip install --no-cache-dir ./packages/workflo-schema \
    && pip install --no-cache-dir ./packages/workflo-utils \
    && pip install --no-cache-dir ./packages/sandbox-isolation \
    && pip install --no-cache-dir ./packages/cortex-auth \
    && pip install --no-cache-dir ./packages/probe-engine \
    && pip install --no-cache-dir ./apps/sandbox-executor \
    && pip install --no-cache-dir ".[postgres]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
