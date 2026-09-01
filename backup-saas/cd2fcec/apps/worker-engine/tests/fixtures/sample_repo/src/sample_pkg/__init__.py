"""sample_pkg — a tiny fixture module with intentional edge cases.

Deliberately exposes a small, well-defined surface so workflo tests can:

  1. Surface-tier: run pytest against `tests/test_native.py` and get a
     deterministic count (3 passing) — this is the baseline output a
     --test run produces, no model.

  2. Deep / aggressive tier: the worker engine's `_run_model_stage`
     DROPS an additional pytest file at `tests/test_workflo_generated.py`
     derived from ProbeSpecs the model proposed. Those tests are pass-
     through (they `assert True`) so the deep run reports MORE total
     tests than the surface run — that's the observable, receipt-
     auditable difference between `--test` and `--deep-test`.

Keeping the surface count small (3) means a deep run that adds, say,
5 model probes produces total=8 — easily distinguishable from total=3.
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Add two integers. Kept trivial on purpose — the fixture is about
    test plumbing, not arithmetic correctness."""
    return a + b


def divide(numerator: float, denominator: float) -> float:
    """Divide, raising ZeroDivisionError on a zero denominator.

    Surface tests check the happy path. Deep-test generated probes are
    expected to add the zero-denominator case (and any other edge cases
    the model proposes) so the deep run's test file legitimately differs
    from the surface one.
    """
    if denominator == 0:
        raise ZeroDivisionError("denominator must not be zero")
    return numerator / denominator


def is_host_blocked(host: str) -> bool:
    """Return True if the host is on the egress blocklist.

    This is a synthetic helper for the security/canary tests: the worker
    verifies that outbound connections from inside the sandbox fail, and
    `is_host_blocked` lets a fixture test assert "expected blocked host"
    without actually touching the network.
    """
    blocked = {"evil.example.com", "exfil.test", "malware.invalid"}
    return host in blocked
