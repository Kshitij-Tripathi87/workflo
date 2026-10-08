FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by git (for shallow clones) + curl (for ollama, if needed later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy local shared packages first (worker depends on them)
COPY packages/workflo-schema/ /app/packages/workflo-schema/
COPY packages/workflo-utils/ /app/packages/workflo-utils/
COPY packages/probe-engine/ /app/packages/probe-engine/

# Install the shared packages
RUN pip install --no-cache-dir /app/packages/workflo-schema \
    && pip install --no-cache-dir /app/packages/workflo-utils \
    && pip install --no-cache-dir /app/packages/probe-engine

# Common PEP 517 build backends so the offline repo install
# (`pip install --no-deps --no-build-isolation .`) works for modern repos —
# setuptools, flit (click, flask), hatchling (many 2023+ repos), poetry-core.
# Pure-Python, tiny; without these the offline install can't build the
# repo's wheel and its tests can't import the package.
RUN pip install --no-cache-dir flit-core hatchling poetry-core

# Now copy and install the worker itself
COPY apps/worker-engine/pyproject.toml /app/worker-engine/pyproject.toml
COPY apps/worker-engine/src/ /app/worker-engine/src/

# Install the worker (excludes playwright dep via optional extras not required here)
# NOTE: pyproject lists playwright as a hard dep, so pip will try to install it as a wheel
# (small Python package), but won't trigger the ~500MB Chromium binary download unless
# `playwright install` is run. The Chromium download is deferred to a separate image
# (workflo-worker-browser:latest) which adds the binary layer on top of this base.
RUN pip install --no-cache-dir /app/worker-engine

ENV WORKER_MODE=queue
ENV PYTHONUNBUFFERED=1

WORKDIR /app/worker-engine
CMD ["python", "-m", "workflo_worker.main"]
