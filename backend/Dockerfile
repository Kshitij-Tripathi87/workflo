# Cortex Autopilot backend - multi-stage build with aggressive pruning
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# Minimal runtime deps only — no compilers, no headers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 cortex

COPY --from=builder /root/.local /home/cortex/.local
COPY app ./app
COPY alembic.ini ./
COPY pytest.ini ./

ENV PATH=/home/cortex/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=prod

USER cortex

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
