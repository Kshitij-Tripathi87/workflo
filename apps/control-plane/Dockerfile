FROM python:3.11-slim

WORKDIR /app

COPY apps/control-plane/pyproject.toml ./
COPY apps/control-plane/app/ ./app/
COPY apps/control-plane/db/ ./db/
COPY packages/ ./packages/
COPY apps/sandbox-executor/ ./apps/sandbox-executor/
RUN pip install --no-cache-dir ./packages/workflo-schema \
    && pip install --no-cache-dir ./packages/workflo-utils \
    && pip install --no-cache-dir ./packages/sandbox-isolation \
    && pip install --no-cache-dir ./packages/cortex-auth \
    && pip install --no-cache-dir ./packages/probe-engine \
    && pip install --no-cache-dir ./apps/sandbox-executor \
    && pip install --no-cache-dir ".[postgres]"

# Runtime defaults support local smoke tests only. Production must explicitly
# provide PostgreSQL, strong secrets, RLS, and credential-sealing configuration.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite+aiosqlite:////tmp/workflo.db

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin workflo \
    && mkdir -p /var/lib/workflo/transparency \
    && chown -R workflo:workflo /var/lib/workflo/transparency

USER workflo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
