"""Result streamer — sends logs and results to the Control Plane.

In Phase 1 (network=none sandbox), the Control Plane is unreachable, so the
streamer ALWAYS also writes lines to stdout. The host-side executor parses
lines starting with `WORKFLO_REPORT:` and `WORKFLO_CANARY:` from the
container's stdout (captured via `docker logs`). This is the contract:
- Anything important enough to log here is also printed to stdout.
- Network POSTs are best-effort; failures under network=none are expected.
"""

import sys
import httpx
from typing import Optional
from workflo_schema import RunSummary
from workflo_utils.config import get_config_value


class ResultStreamer:
    """Streams test logs and final results back to the Control Plane API.

    ALWAYS also writes log lines to stdout. This is intentional — when the
    sandbox is on `--network none`, the only channel back to the executor
    is the container's stdout (via `docker logs`).
    """

    def __init__(self, run_id: str, control_plane_url: Optional[str] = None, api_key: Optional[str] = None):
        self.run_id = run_id
        self.control_plane_url = control_plane_url or get_config_value("defaults.api_base_url", "http://localhost:8000")
        self.api_key = api_key or get_config_value("auth.api_key", "")
        self._log_buffer: list[str] = []

    @property
    def _headers(self) -> dict:
        return {"X-TenantShield-Key": self.api_key}

    def log(self, line: str) -> None:
        """Send a log line to the Control Plane AND to stdout.

        The stdout write is critical — it's how the executor (which parses
        container stdout via `docker logs`) sees the WORKFLO_REPORT: and
        WORKFLO_CANARY: lines. POST failures under network=none are expected.
        """
        self._log_buffer.append(line)
        # ALWAYS print to stdout — the executor parses these lines from
        # container stdout (captured via `docker logs`).
        try:
            print(line, flush=True)
        except Exception:
            # If stdout is broken we have nothing else to do — but the line
            # is still in the buffer for later inspection if asked.
            pass
        # Best-effort POST to Control Plane. Under network=none this fails —
        # that's by design and not an error.
        try:
            with httpx.Client(headers=self._headers, timeout=10) as client:
                client.post(
                    f"{self.control_plane_url}/v1/runs/{self.run_id}/logs",
                    params={"log_line": line},
                )
        except Exception:
            pass

    def complete(self, summary: RunSummary) -> None:
        """Signal run completion with the final summary."""
        try:
            with httpx.Client(headers=self._headers, timeout=30) as client:
                client.post(
                    f"{self.control_plane_url}/v1/runs/{self.run_id}/complete",
                    json=summary.model_dump(),
                )
        except Exception:
            pass

    def fail(self, error: str) -> None:
        """Signal run failure."""
        try:
            with httpx.Client(headers=self._headers, timeout=30) as client:
                client.post(
                    f"{self.control_plane_url}/v1/runs/{self.run_id}/complete",
                    json={"status": "failed", "error": error},
                )
        except Exception:
            pass
