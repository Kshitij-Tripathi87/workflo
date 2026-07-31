FROM python:3.11-slim

LABEL org.opencontainers.image.title="Cortex Autopilot Impact Gate"
LABEL org.opencontainers.image.description="Block risky data changes before they reach production"

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir httpx==0.27.* pyyaml==6.* pydantic==2.*

COPY entrypoint.py /entrypoint.py
COPY notify_slack.py /notify_slack.py
COPY report.py /report.py
COPY cortex_lib.py /cortex_lib.py

ENTRYPOINT ["python", "/entrypoint.py"]
