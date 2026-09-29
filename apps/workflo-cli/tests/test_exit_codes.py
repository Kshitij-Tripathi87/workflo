"""Phase 7 exit-code contract tests (run_contract.md §6).

These tests pin the stable behavior Workflo callers may rely on. If
this file has to change, so does the public API.
"""

import pytest

from workflo_cli.exit_codes import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_EXECUTION_FAILED,
    EXIT_INFRASTRUCTURE_ERROR,
    EXIT_POLICY_BLOCKED,
    EXIT_VERIFICATION_FAILED,
    EXIT_VERIFIED,
    EXIT_VERIFIED_WITH_FINDINGS,
    classify_config_error,
    classify_infra_error,
    classify_run_outcome,
    CODE_NAMES,
)


class TestContractCodesPinned:
    def test_codes_match_contract(self):
        assert EXIT_VERIFIED == 0
        assert EXIT_VERIFIED_WITH_FINDINGS == 1
        assert EXIT_POLICY_BLOCKED == 2
        assert EXIT_EXECUTION_FAILED == 3
        assert EXIT_VERIFICATION_FAILED == 4
        assert EXIT_CONFIGURATION_ERROR == 5
        assert EXIT_INFRASTRUCTURE_ERROR == 6

    def test_names_cover_codes(self):
        assert len(CODE_NAMES) == 7
        for code in range(7):
            assert code in CODE_NAMES


class TestRunClassification:
    def test_clean_run_is_verified(self):
        assert classify_run_outcome(True, failed_tests=0, findings_count=0) == 0

    def test_failed_tests_is_verified_with_findings(self):
        assert classify_run_outcome(True, failed_tests=2) == 1

    def test_findings_only_is_verified_with_findings(self):
        assert classify_run_outcome(True, findings_count=1) == 1

    def test_failed_run_is_never_zero(self):
        # A run that failed teardown *cannot* be clean — never 0.
        assert classify_run_outcome(False) == 1

    def test_config_and_infra_are_distinct(self):
        assert classify_config_error() == 5
        assert classify_infra_error() == 6
