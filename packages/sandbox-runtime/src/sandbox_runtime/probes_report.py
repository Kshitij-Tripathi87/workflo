"""In-sandbox isolation probe report — executed INSIDE the sandbox.

The supervisor launches this module via bwrap so the isolation probes
observe the sandbox's own view of the world (its mount table, its PID
namespace, its network namespace) — never the host's. Probes running on
the host would prove nothing about the sandbox.

Emits a single JSON object on stdout:

    {
      "probes": [{"name": ..., "passed": ..., "detail": ..., "severity": ...}],
      "canary": {"target_host": ..., "request_succeeded": ..., "error": ...}
    }

The canary is the Claim #3 egress check: a real outbound connection
attempt that MUST fail in a correctly sealed sandbox.
"""

from __future__ import annotations

import json
import socket
import sys
from dataclasses import asdict

from sandbox_runtime.probes import IsolationProbes

# The canary target — a stable, well-known external endpoint. Reaching it
# from inside the sandbox means network isolation is BROKEN.
CANARY_HOST = "8.8.8.8"
CANARY_PORT = 53


def run_canary() -> dict:
    """Attempt a real outbound connection. Expected to FAIL."""
    target = f"{CANARY_HOST}:{CANARY_PORT}"
    try:
        sock = socket.create_connection((CANARY_HOST, CANARY_PORT), timeout=3)
        sock.close()
        return {
            "target_host": target,
            "request_succeeded": True,
            "error": None,
        }
    except Exception as e:
        return {
            "target_host": target,
            "request_succeeded": False,
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> int:
    probes = IsolationProbes(sandbox_pid=1).run_all()
    canary = run_canary()

    report = {
        "probes": [asdict(p) for p in probes],
        "canary": canary,
    }
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
