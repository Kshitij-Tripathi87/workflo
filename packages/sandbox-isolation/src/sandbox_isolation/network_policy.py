"""Network policy — egress is locked down by default, not configured open.

The default state for any Airlock sandbox is: cannot reach the internet.
This is the opposite of how most tools approach network policy (open by
default, restrict on demand). For a privacy guarantee to be architectural
rather than promised, the default has to be the safe one.

If a sandbox needs to reach the Control Plane status endpoint, it gets
explicitly allowlisted. If it needs to reach the OSS model registry to
download weights at build time, that's at image-build time, never at
run time.
"""

from __future__ import annotations

import socket
import urllib.request
import urllib.error
import ssl
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional


# Default: no external hosts. The sandbox can reach only itself.
# The Control Plane status endpoint is added at sandbox-creation time
# by the executor, not hardcoded here.
DEFAULT_BLOCKED_EGRESS: list[str] = []  # explicit allowlist, not blocklist


def build_isolation_args(
    allowed_egress_hosts: list[str],
    control_plane_host: Optional[str] = None,
) -> dict:
    """Build the network isolation arguments for a sandbox container.

    Returns a dict the Docker wrapper can pass to `docker run`:
        {
          "network_mode": "none",  # default: no network at all
          "add_hosts": [...],      # only if control_plane_host is set
          "dns": [],               # empty — no DNS resolution by default
        }

    The principle: if a sandbox CAN reach a host, it has to be on this list.
    There is no "allow everything except X" path.
    """

    args: dict = {
        "network_mode": "none",
        "dns": [],
        "add_hosts": [],
    }

    if control_plane_host:
        # Resolve once at sandbox creation, not at runtime.
        try:
            ip = socket.gethostbyname(control_plane_host)
            args["add_hosts"].append(f"{control_plane_host}:{ip}")
        except socket.gaierror:
            # If we can't resolve the control plane host at creation time,
            # we refuse to start the sandbox — better than a half-isolated run.
            raise RuntimeError(
                f"Cannot resolve control plane host '{control_plane_host}' "
                f"at sandbox creation. Refusing to start with degraded isolation."
            )

    # Even if caller passes allowed_egress_hosts, we DO NOT add them to
    # add_hosts at runtime — that's a configuration decision made at image
    # build time, not per-run. The runtime sandbox is sealed.
    _ = allowed_egress_hosts  # explicitly ignored — see module docstring

    return args


@dataclass
class CanaryResult:
    """Result of an outbound-canary check from inside the sandbox."""

    attempted_at: datetime
    target_host: str
    request_succeeded: bool
    error: Optional[str]


def attempt_canary_request(
    target_host: str = "https://example.com",
    timeout_seconds: float = 3.0,
) -> CanaryResult:
    """Make an outbound HTTPS request and report whether it succeeded.

    Run this FROM INSIDE the sandbox. The expected result is failure
    (request_succeeded=False). If it succeeds, the network isolation
    is broken and the run MUST be flagged.

    This is the mechanism that backs Claim #3 of the Scope Contract.
    """

    attempted_at = datetime.now(UTC)

    # stdlib only — we don't want a dependency on httpx/requests for this
    # critical check, because a sandbox's network isolation MUST NOT depend
    # on packages pulled from PyPI. Imports are at module level so tests
    # can monkeypatch them.
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(target_host, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ctx) as resp:
            return CanaryResult(
                attempted_at=attempted_at,
                target_host=target_host,
                request_succeeded=True,
                error=None,
            )
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return CanaryResult(
            attempted_at=attempted_at,
            target_host=target_host,
            request_succeeded=False,
            error=str(e),
        )
    except Exception as e:
        # Any unexpected exception is also a failure for canary purposes —
        # we want to know about it.
        return CanaryResult(
            attempted_at=attempted_at,
            target_host=target_host,
            request_succeeded=False,
            error=f"unexpected: {type(e).__name__}: {e}",
        )
