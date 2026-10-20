"""Unit tests for train/functional_checks.py (gate v2, Path A).

These run without any model: each check operates on a dataset-style record
plus a parsed payload. Valid fixtures mirror real dataset records; invalid
fixtures each violate exactly one rule so regressions pinpoint the rule.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "functional_checks", _ROOT / "train" / "functional_checks.py"
)
functional_checks = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("functional_checks", functional_checks)
_SPEC.loader.exec_module(functional_checks)

TEST_GEN_RECORD = {
    "system": "You generate pytest test files for a repository change.",
    "user": (
        "Module: app/services/cart.py\n"
        "Function: compute_total(lines: list[tuple[str, int, int]]) -> int\n"
        "Behavior: returns the summed quantity * unit_price_cents in cents. "
        "Empty cart returns 0. A negative quantity raises ValueError."
    ),
}

TEST_GEN_PAYLOAD = {
    "path": "workflo_generated_tests/test_cart_total.py",
    "content": (
        '"""Generated tests for cart total computation."""\n'
        "import pytest\n"
        "\n"
        "from app.services.cart import compute_total\n"
        "\n"
        "\n"
        "def test_compute_total_sums_line_items():\n"
        '    lines = [("sku-1", 2, 500), ("sku-2", 1, 1250)]\n'
        "    assert compute_total(lines) == 2250\n"
        "\n"
        "\n"
        "def test_compute_total_empty_cart_returns_zero():\n"
        "    assert compute_total([]) == 0\n"
        "\n"
        "\n"
        "def test_compute_total_rejects_negative_quantity():\n"
        "    with pytest.raises(ValueError):\n"
        '        compute_total([("sku-1", -1, 500)])\n'
    ),
    "framework": "pytest",
    "rationale": "Covers summation, empty cart, and the ValueError branch.",
}

REASONING_RECORD = {
    "system": "You propose a property-based invariant for one function.",
    "user": (
        "Function under analysis: app.rbac.enforce(role: str, action: str) -> bool\n"
        "Role hierarchy: admin > editor > viewer; unknown roles deny everything. "
        "Propose the deny-by-default invariant."
    ),
}

REASONING_PAYLOAD = {
    "description": "Any role not present in the known role table must be denied.",
    "target": "app.rbac.enforce",
    "category": "auth",
    "hypothesis_strategy": (
        'st.tuples(st.text(min_size=1, max_size=24), '
        'st.sampled_from(["read", "write", "delete"]))'
    ),
    "property_check": "(role in KNOWN_ROLES) or (not enforce(role, action))",
}

REPORTING_RECORD = {
    "system": "You summarize automated test results.",
    "user": (
        '{"run_id": "run-a01f", "totals": {"passed": 8, "failed": 1, '
        '"error": 0, "timeout": 0, "not_run": 0}, "duration_ms": 15300, '
        '"failures": [{"test": "test_receipt_tamper_rejection", '
        '"outcome": "FAILED", "duration_ms": 940}]}'
    ),
}

REPORTING_PAYLOAD = {
    "summary": (
        "8 of 9 tests passed. The receipt tamper-rejection test failed, which is "
        "a security-relevant regression. Treat this as a release blocker."
    ),
    "findings": [
        {
            "root_cause": "tampered receipts are no longer rejected by the verifier",
            "affected_tests": ["test_receipt_tamper_rejection"],
            "severity": "high",
            "explanation": "Modified receipts must never verify.",
        }
    ],
    "priority_order": ["tampered receipts are no longer rejected by the verifier"],
}


class TestTestGen:
    def test_valid_payload_passes(self):
        result = functional_checks.check_test_gen(TEST_GEN_RECORD, TEST_GEN_PAYLOAD)
        assert result.ok, result.reasons

    def test_missing_assertions_fails(self):
        payload = {
            **TEST_GEN_PAYLOAD,
            "content": (
                "import pytest\n"
                "from app.services.cart import compute_total\n"
                "\n"
                "\n"
                "def test_compute_total_sums_line_items():\n"
                '    compute_total([("sku-1", 2, 500)])\n'
            ),
        }
        result = functional_checks.check_test_gen(TEST_GEN_RECORD, payload)
        assert not result.ok
        assert any("assert" in reason for reason in result.reasons)

    def test_module_not_imported_fails(self):
        payload = {
            **TEST_GEN_PAYLOAD,
            "content": (
                "import pytest\n"
                "\n"
                "\n"
                "def test_something():\n"
                "    assert 1 + 1 == 2\n"
            ),
        }
        result = functional_checks.check_test_gen(TEST_GEN_RECORD, payload)
        assert not result.ok
        assert any("imported" in reason for reason in result.reasons)

    def test_function_never_called_fails(self):
        payload = {
            **TEST_GEN_PAYLOAD,
            "content": (
                "import pytest\n"
                "from app.services.cart import compute_total\n"
                "\n"
                "\n"
                "def test_unrelated_thing():\n"
                "    assert 1 + 1 == 2\n"
            ),
        }
        result = functional_checks.check_test_gen(TEST_GEN_RECORD, payload)
        assert not result.ok
        assert any("never called" in reason for reason in result.reasons)

    def test_prohibited_import_fails(self):
        payload = {
            **TEST_GEN_PAYLOAD,
            "content": (
                "import pytest\n"
                "import subprocess\n"
                "from app.services.cart import compute_total\n"
                "\n"
                "\n"
                "def test_compute_total_sums_line_items():\n"
                "    assert compute_total([]) == 0\n"
            ),
        }
        result = functional_checks.check_test_gen(TEST_GEN_RECORD, payload)
        assert not result.ok
        assert any("subprocess" in reason for reason in result.reasons)

    @pytest.mark.skipif(
        importlib.util.find_spec("pytest") is None, reason="pytest unavailable"
    )
    def test_pytest_collection_rejects_broken_import(self):
        payload = {
            **TEST_GEN_PAYLOAD,
            "content": (
                "import pytest\n"
                "from app.services.cart import compute_total, does_not_exist\n"
                "\n"
                "\n"
                "def test_compute_total_sums_line_items():\n"
                "    assert compute_total([]) == 0\n"
            ),
        }
        reasons = functional_checks.pytest_collect_check(
            TEST_GEN_RECORD, payload["content"]
        )
        assert reasons, "collection should fail on unresolvable import"


class TestReasoning:
    def test_valid_payload_passes(self):
        result = functional_checks.check_reasoning(REASONING_RECORD, REASONING_PAYLOAD)
        assert result.ok, result.reasons

    def test_target_mismatch_fails(self):
        payload = {**REASONING_PAYLOAD, "target": "app.auth.login"}
        result = functional_checks.check_reasoning(REASONING_RECORD, payload)
        assert not result.ok
        assert any("does not match" in reason for reason in result.reasons)

    @pytest.mark.skipif(
        importlib.util.find_spec("hypothesis") is None,
        reason="hypothesis unavailable",
    )
    def test_non_strategy_expression_fails(self):
        payload = {
            **REASONING_PAYLOAD,
            "hypothesis_strategy": "st.nope_not_a_strategy(3)",
        }
        result = functional_checks.check_reasoning(REASONING_RECORD, payload)
        assert not result.ok

    def test_result_variable_property_passes(self):
        # Invariants may reference the function's result or maintained state.
        scope_record = {
            "user": (
                "Function under analysis: app.tenants.scope(query, tenant_id)\n"
                "query is a select over a shared table; scope must add a tenant filter."
            )
        }
        payload = {
            **REASONING_PAYLOAD,
            "target": "app.tenants.scope",
            "property_check": "all(row.tenant_id == tenant_id for row in scoped_query)",
        }
        result = functional_checks.check_reasoning(scope_record, payload)
        assert result.ok, result.reasons

    def test_ungrounded_property_fails(self):
        payload = {**REASONING_PAYLOAD, "property_check": "(alpha > beta)"}
        result = functional_checks.check_reasoning(REASONING_RECORD, payload)
        assert not result.ok
        assert any("ungrounded" in reason for reason in result.reasons)

    def test_property_without_comparison_fails(self):
        payload = {**REASONING_PAYLOAD, "property_check": "enforce(role, action)"}
        result = functional_checks.check_reasoning(REASONING_RECORD, payload)
        assert not result.ok
        assert any("falsifiable" in reason for reason in result.reasons)

    def test_strategy_with_foreign_name_fails(self):
        payload = {
            **REASONING_PAYLOAD,
            "hypothesis_strategy": "st.lists(others.source())",
        }
        result = functional_checks.check_reasoning(REASONING_RECORD, payload)
        assert not result.ok
        assert any("non-strategy names" in reason for reason in result.reasons)


class TestReporting:
    def test_valid_payload_passes(self):
        result = functional_checks.check_reporting(REPORTING_RECORD, REPORTING_PAYLOAD)
        assert result.ok, result.reasons

    def test_invented_test_name_fails(self):
        payload = {
            **REPORTING_PAYLOAD,
            "findings": [
                {
                    **REPORTING_PAYLOAD["findings"][0],
                    "affected_tests": ["test_receipt_tamper_rejection", "test_ghost"],
                }
            ],
        }
        result = functional_checks.check_reporting(REPORTING_RECORD, payload)
        assert not result.ok
        assert any("invented" in reason for reason in result.reasons)

    def test_missing_coverage_fails(self):
        record = {
            "user": (
                '{"totals": {"failed": 2}, "failures": ['
                '{"test": "test_a", "outcome": "FAILED"}, '
                '{"test": "test_b", "outcome": "FAILED"}]}'
            )
        }
        payload = {
            "summary": "1 of 2 tests failed; test_a is broken.",
            "findings": [
                {
                    "root_cause": "a is broken",
                    "affected_tests": ["test_a"],
                    "severity": "high",
                    "explanation": "a regressed.",
                }
            ],
            "priority_order": ["a is broken"],
        }
        result = functional_checks.check_reporting(record, payload)
        assert not result.ok
        assert any("not covered" in reason for reason in result.reasons)

    def test_priority_entry_not_a_root_cause_fails(self):
        payload = {**REPORTING_PAYLOAD, "priority_order": ["something else"]}
        result = functional_checks.check_reporting(REPORTING_RECORD, payload)
        assert not result.ok
        assert any("priority_order" in reason for reason in result.reasons)

    def test_findings_without_failures_fails(self):
        record = {"user": '{"totals": {"failed": 0}, "failures": []}'}
        result = functional_checks.check_reporting(record, REPORTING_PAYLOAD)
        assert not result.ok
        assert any("no failures" in reason for reason in result.reasons)

    def test_grounded_info_note_on_green_run_passes(self):
        record = {
            "user": (
                '{"totals": {"passed": 40, "failed": 0}, "failures": [], '
                '"notes": "14 deprecation warnings emitted from legacy_client"}'
            )
        }
        payload = {
            "summary": "All 40 tests passed with no failures.",
            "findings": [
                {
                    "root_cause": "deprecation warnings emitted from legacy_client",
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": "Informational only.",
                }
            ],
            "priority_order": ["deprecation warnings emitted from legacy_client"],
        }
        result = functional_checks.check_reporting(record, payload)
        assert result.ok, result.reasons

    def test_ungrounded_finding_on_green_run_fails(self):
        record = {
            "user": '{"totals": {"passed": 40, "failed": 0}, "failures": []}'
        }
        payload = {
            "summary": "All 40 tests passed with no failures.",
            "findings": [
                {
                    "root_cause": "coverage dropped by three percent",
                    "affected_tests": [],
                    "severity": "info",
                    "explanation": "Coverage regression suspected.",
                }
            ],
            "priority_order": ["coverage dropped by three percent"],
        }
        result = functional_checks.check_reporting(record, payload)
        assert not result.ok
        assert any("not grounded" in reason for reason in result.reasons)

    def test_summary_ignoring_failures_fails(self):
        payload = {**REPORTING_PAYLOAD, "summary": "Everything looks great today."}
        result = functional_checks.check_reporting(REPORTING_RECORD, payload)
        assert not result.ok
        assert any("summary" in reason for reason in result.reasons)
