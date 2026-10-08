"""Stable CLI exit codes — the contract documented in run_contract.md §6.

Codes are part of Workflo's PUBLIC developer API. Never changed casually;
a change is a breaking CLI release. The layer splits into:

  * constants — what the code MEANS
  * classify_run_outcome() — mapping from a RunResult to a code (pure)
  * CLI command exit behaviors — kept backward-compatible with the
    pre-Phase-7 tests where they exist; new behavior lands as tests come
    online for the Phase 7 contract.

The mapping below is the reference; the CLI's per-command exit handlers
should call `classify_run_outcome` and keep their behavior stable.
"""

from __future__ import annotations

from typing import Optional


# Exit codes — locked contract
EXIT_VERIFIED = 0                    # clean: verified teardown, no findings
EXIT_VERIFIED_WITH_FINDINGS = 1      # verified but finds/issues reported
EXIT_POLICY_BLOCKED = 2              # policy denied something material
EXIT_EXECUTION_FAILED = 3            # sandbox didn't run such that no receipt can prove
EXIT_VERIFICATION_FAILED = 4         # the receipt's claims failed
EXIT_CONFIGURATION_ERROR = 5         # bad config / bad flags
EXIT_INFRASTRUCTURE_ERROR = 6        # the host can't satisfy the contract


# Canonical names — referenced from docs and tests
CODE_NAMES = {
    EXIT_VERIFIED: "VERIFIED",
    EXIT_VERIFIED_WITH_FINDINGS: "VERIFIED_WITH_FINDINGS",
    EXIT_POLICY_BLOCKED: "POLICY_BLOCKED",
    EXIT_EXECUTION_FAILED: "EXECUTION_FAILED",
    EXIT_VERIFICATION_FAILED: "VERIFICATION_FAILED",
    EXIT_CONFIGURATION_ERROR: "CONFIGURATION_ERROR",
    EXIT_INFRASTRUCTURE_ERROR: "INFRASTRUCTURE_ERROR",
}


def classify_run_outcome(
    success: bool,
    failed_tests: int = 0,
    findings_count: int = 0,
) -> int:
    """Map a run's honest outcome to a stable exit code.

    Rules:
      * teardown-verified + zero failed tests + no findings → VERIFIED (0)
      * teardown-verified but tests failed or findings exist → VERIFIED_WITH_FINDINGS (1)
      * not success → VERIFIED_WITH_FINDINGS (1) — a signed receipt
        still exists carrying the failure (the run HAPPENED, tear-down
        verified), and the caller can inspect it for the truth. The CLI
        keeps its historical semantics here.
    """
    if not success:
        return EXIT_VERIFIED_WITH_FINDINGS
    if failed_tests or findings_count:
        return EXIT_VERIFIED_WITH_FINDINGS
    return EXIT_VERIFIED


def classify_config_error() -> int:
    return EXIT_CONFIGURATION_ERROR


def classify_infra_error() -> int:
    return EXIT_INFRASTRUCTURE_ERROR
