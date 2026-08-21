"""Report-generation tests.

Verify that:
  1. All 4 reporters produce valid files (md, json, sarif, html)
  2. JSON reporter output parses as JSON and has expected keys
  3. SARIF reporter output is valid SARIF 2.1.0
  4. MD reporter includes severity counts + gates + findings
  5. HTML reporter contains severity badges + finding details
  6. Report files are written to disk at the requested location
  7. Findings list flows through to all 4 formats consistently
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate_phase2.orchestrator import (
    Finding,
    GateResult,
    ValidationResult,
)
from validate_phase2.reporters import (
    REPORTERS,
    write_json,
    write_md,
    write_sarif,
    write_html,
)


def _make_result() -> ValidationResult:
    return ValidationResult(
        repo="https://example.com/repo",
        baseline="abc123def456",
        head="def456abc789",
        flags=["architecture", "security"],
        model="Qwen/Qwen2.5-Coder-7B-AWQ",
        started_at="2026-08-21T00:00:00Z",
        finished_at="2026-08-21T00:01:00Z",
        gates=[
            GateResult(name="import-check", passed=True, duration_s=2.0,
                       stdout_tail="OK\n", stderr_tail="", command="python -c"),
            GateResult(name="pytest", passed=False, duration_s=10.5,
                       stdout_tail="3 passed", stderr_tail="FAILED test_x",
                       command="python -m pytest"),
        ],
        findings=[
            Finding(id="ARCH-001", severity="high", category="async-patterns",
                    file="auth.py", line=42, pattern="lazy-load-in-async",
                    message="user.org triggers sync DB load",
                    suggestion="Use await db.get(Organization, user.org_id)",
                    baseline_regression=True),
            Finding(id="ARCH-002", severity="medium", category="patterns",
                    file="main.py", line=10, pattern="duplicated-logic",
                    message="Same token-claim building in 3 places",
                    suggestion="Extract build_access_token_claims()",
                    baseline_regression=False),
            Finding(id="ARCH-003", severity="info", category="oauth",
                    file="oauth.py", line=1, pattern="informational",
                    message="Token rotation is correct",
                    suggestion="",
                    baseline_regression=False),
        ],
        notes="LLM analysis complete.",
    )


class TestAllReportersProduceFiles:
    """Each reporter must write a file with non-trivial content."""

    @pytest.mark.parametrize("fmt", ["md", "json", "sarif", "html"])
    def test_reporter_writes_file(self, fmt, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / f"report.{fmt}"
        REPORTERS[fmt](result, out)
        assert out.exists(), f"{fmt} reporter did not write {out}"
        assert out.stat().st_size > 100, f"{fmt} file is suspiciously small"


class TestJsonReporter:

    def test_json_parses(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.json"
        write_json(result, out)
        data = json.loads(out.read_text())
        assert isinstance(data, dict)

    def test_json_has_expected_keys(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.json"
        write_json(result, out)
        data = json.loads(out.read_text())
        for key in ["repo", "baseline", "head", "flags", "model",
                    "started_at", "finished_at", "gates",
                    "summary", "findings", "notes"]:
            assert key in data, f"Missing key: {key}"

    def test_json_severity_counts_match(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.json"
        write_json(result, out)
        data = json.loads(out.read_text())
        assert data["summary"] == {"critical": 0, "high": 1, "medium": 1, "low": 0, "info": 1}

    def test_json_findings_complete(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.json"
        write_json(result, out)
        data = json.loads(out.read_text())
        assert len(data["findings"]) == 3
        ids = {f["id"] for f in data["findings"]}
        assert ids == {"ARCH-001", "ARCH-002", "ARCH-003"}


class TestSarifReporter:

    def test_sarif_has_required_fields(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.sarif"
        write_sarif(result, out)
        data = json.loads(out.read_text())
        assert data["version"] == "2.1.0"
        assert "runs" in data
        assert len(data["runs"]) == 1
        assert "$schema" in data

    def test_sarif_tool_driver(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.sarif"
        write_sarif(result, out)
        data = json.loads(out.read_text())
        driver = data["runs"][0]["tool"]["driver"]
        assert driver["name"] == "validate-phase2"
        assert "rules" in driver
        assert "version" in driver

    def test_sarif_results_match_findings(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.sarif"
        write_sarif(result, out)
        data = json.loads(out.read_text())
        results = data["runs"][0]["results"]
        assert len(results) == 3
        rule_ids = {r["ruleId"] for r in results}
        assert rule_ids == {"ARCH-001", "ARCH-002", "ARCH-003"}

    def test_sarif_levels_correct(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.sarif"
        write_sarif(result, out)
        data = json.loads(out.read_text())
        results = data["runs"][0]["results"]
        levels = {r["ruleId"]: r["level"] for r in results}
        # high → error, medium → warning, info → note (per SEVERITY_TO_SARIF_LEVEL)
        assert levels["ARCH-001"] == "error"
        assert levels["ARCH-002"] == "warning"
        assert levels["ARCH-003"] == "note"

    def test_sarif_locations_have_line_numbers(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.sarif"
        write_sarif(result, out)
        data = json.loads(out.read_text())
        results = data["runs"][0]["results"]
        for r in results:
            assert "locations" in r
            assert len(r["locations"]) >= 1
            assert "startLine" in r["locations"][0]["physicalLocation"]["region"]


class TestMarkdownReporter:

    def test_md_has_summary(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.md"
        write_md(result, out)
        text = out.read_text(encoding="utf-8")
        assert "# Architecture Review" in text
        assert "## Summary" in text
        assert "## Gates" in text
        assert "## Findings" in text

    def test_md_severity_counts(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.md"
        write_md(result, out)
        text = out.read_text(encoding="utf-8")
        assert "High | 1" in text
        assert "Medium | 1" in text
        assert "Info | 1" in text

    def test_md_findings_sorted_by_severity(self, temp_work_dir):
        """Critical/high should appear before low/info."""
        result = _make_result()
        out = temp_work_dir / "r.md"
        write_md(result, out)
        text = out.read_text(encoding="utf-8")
        idx_high = text.find("ARCH-001")
        idx_med = text.find("ARCH-002")
        idx_info = text.find("ARCH-003")
        assert 0 < idx_high < idx_med < idx_info

    def test_md_failed_gate_detail_shown(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.md"
        write_md(result, out)
        text = out.read_text(encoding="utf-8")
        assert "Failed Gate Detail" in text
        assert "FAILED test_x" in text


class TestHtmlReporter:

    def test_html_has_doctype(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.html"
        write_html(result, out)
        text = out.read_text()
        assert text.startswith("<!doctype html>")

    def test_html_has_all_findings(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.html"
        write_html(result, out)
        text = out.read_text()
        for fid in ["ARCH-001", "ARCH-002", "ARCH-003"]:
            assert fid in text, f"Finding {fid} missing from HTML report"

    def test_html_has_severity_classes(self, temp_work_dir):
        result = _make_result()
        out = temp_work_dir / "r.html"
        write_html(result, out)
        text = out.read_text()
        assert "sev-high" in text
        assert "sev-medium" in text
        assert "sev-info" in text

    def test_html_escapes_user_content(self, temp_work_dir):
        """HTML-escape: a <script> tag in a message must not render as a tag."""
        result = _make_result()
        result.findings[0].message = "<script>alert('xss')</script>"
        out = temp_work_dir / "r.html"
        write_html(result, out)
        text = out.read_text(encoding="utf-8")
        # Raw <script>alert('xss')</script> from user input must NOT appear
        assert "<script>alert('xss')</script>" not in text
        # The HTML-escaped form <script>alert MUST appear instead
        assert "&lt;script&gt;alert" in text
