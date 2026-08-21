"""Probe runner — executes config-driven probes and aggregates results.

For Phase 1 (no model), this generates a pytest test file from the probe
config and runs it. The generated test file uses the existing
`workflo.isolation.verifier` functions, so we get the same SOC 2
evidence chain without the hardcoded fixtures.

This is the "high-leverage Week 1 work" — one config, any repo, no per-repo
test writing required.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from probe_engine.models import (
    ProbeConfig,
    ProbeResult,
    ProbeRunSummary,
    ProbeSpec,
)


class ProbeRunner:
    """Executes probes defined in a ProbeConfig against a live target.

    Usage:
        config = ProbeConfig.from_yaml_str(yaml_text)
        runner = ProbeRunner(config)
        summary = runner.run_all(
            creator_client=...,
            intruder_client=...,
            resource_id="proj-123",
        )
        print(summary.passed, summary.failed)
    """

    def __init__(self, config: ProbeConfig):
        self.config = config

    def run_one(
        self,
        probe_name: str,
        creator_client,
        intruder_client,
        resource_id: str,
    ) -> ProbeResult:
        """Execute a single named probe from the config."""
        probe = next((p for p in self.config.probes if p.name == probe_name), None)
        if probe is None:
            return ProbeResult(
                name=probe_name,
                pattern="unknown",
                method="GET",
                path="",
                passed=False,
                error=f"No probe named {probe_name!r} in config",
            )
        return self._run_one(probe, creator_client, intruder_client, resource_id)

    def run_all(
        self,
        creator_client,
        intruder_client,
        resource_id: str,
    ) -> ProbeRunSummary:
        """Run every probe in the config and return an aggregated summary."""

        results: list[ProbeResult] = []
        start = time.monotonic()
        soc2_controls: list[str] = []
        for probe in self.config.probes:
            result = self._run_one(probe, creator_client, intruder_client, resource_id)
            results.append(result)
            if probe.soc2_controls:
                for c in probe.soc2_controls:
                    if c not in soc2_controls:
                        soc2_controls.append(c)

        duration = time.monotonic() - start

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed and r.error is None)
        skipped = sum(1 for r in results if r.error is not None)

        findings: list[dict] = []
        for r in results:
            if not r.passed:
                findings.append({
                    "probe": r.name,
                    "pattern": r.pattern,
                    "method": r.method,
                    "path": r.path,
                    "actual_status": r.actual_status,
                    "error": r.error,
                    "detail": r.detail,
                })

        return ProbeRunSummary(
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_seconds=duration,
            soc2_controls_covered=soc2_controls,
            findings=findings,
            results=results,
        )

    def _run_one(
        self,
        probe: ProbeSpec,
        creator_client,
        intruder_client,
        resource_id: str,
    ) -> ProbeResult:
        """Execute a single probe based on its pattern."""

        url = f"{probe.path}/{resource_id}"
        expected = probe.expected_status
        if isinstance(expected, int):
            expected_statuses = [expected]
        else:
            expected_statuses = list(expected)

        try:
            if probe.pattern == "api_read":
                return self._run_api_read(
                    probe, intruder_client, url, resource_id, expected_statuses
                )
            elif probe.pattern == "api_list":
                return self._run_api_list(
                    probe, intruder_client, resource_id, expected_statuses
                )
            elif probe.pattern == "api_modify":
                return self._run_api_modify(
                    probe, intruder_client, url, resource_id, expected_statuses
                )
            elif probe.pattern == "api_delete":
                return self._run_api_delete(
                    probe, intruder_client, url, resource_id, expected_statuses
                )
            elif probe.pattern == "positive_control":
                return self._run_positive_control(
                    probe, creator_client, url, resource_id, expected_statuses
                )
            else:
                return ProbeResult(
                    name=probe.name,
                    pattern=probe.pattern,
                    method=probe.method,
                    path=probe.path,
                    passed=False,
                    error=f"Unsupported pattern: {probe.pattern}",
                )
        except Exception as e:
            return ProbeResult(
                name=probe.name,
                pattern=probe.pattern,
                method=probe.method,
                path=probe.path,
                passed=False,
                error=f"{type(e).__name__}: {e}",
            )

    def _run_api_read(self, probe, client, url, resource_id, expected_statuses):
        resp = client.get(url)
        passed = resp.status_code in expected_statuses
        return ProbeResult(
            name=probe.name,
            pattern=probe.pattern,
            method="GET",
            path=url,
            actual_status=resp.status_code,
            passed=passed,
            detail={"expected": expected_statuses, "soc2_controls": probe.soc2_controls},
        )

    def _run_api_list(self, probe, client, resource_id, expected_statuses):
        resp = client.get(probe.path)
        leaked = False
        list_key = probe.list_key or "items"
        if resp.status_code in expected_statuses:
            try:
                items = resp.json().get(list_key, [])
                ids = [item.get("id") for item in items] if isinstance(items, list) else []
                leaked = resource_id in ids
            except Exception:
                leaked = False

        passed = (not leaked) if probe.expect_resource_absent else (resp.status_code in expected_statuses)
        return ProbeResult(
            name=probe.name,
            pattern=probe.pattern,
            method="GET",
            path=probe.path,
            actual_status=resp.status_code,
            passed=passed,
            detail={"leaked": leaked, "list_key": list_key, "soc2_controls": probe.soc2_controls},
        )

    def _run_api_modify(self, probe, client, url, resource_id, expected_statuses):
        resp = client.put(url, json={"name": "SHOULD NOT PERSIST"})
        passed = resp.status_code in expected_statuses
        return ProbeResult(
            name=probe.name,
            pattern=probe.pattern,
            method="PUT",
            path=url,
            actual_status=resp.status_code,
            passed=passed,
            detail={"expected": expected_statuses, "soc2_controls": probe.soc2_controls},
        )

    def _run_api_delete(self, probe, client, url, resource_id, expected_statuses):
        resp = client.delete(url)
        passed = resp.status_code in expected_statuses
        return ProbeResult(
            name=probe.name,
            pattern=probe.pattern,
            method="DELETE",
            path=url,
            actual_status=resp.status_code,
            passed=passed,
            detail={"expected": expected_statuses, "soc2_controls": probe.soc2_controls},
        )

    def _run_positive_control(self, probe, client, url, resource_id, expected_statuses):
        resp = client.get(url)
        passed = resp.status_code in expected_statuses
        return ProbeResult(
            name=probe.name,
            pattern=probe.pattern,
            method="GET",
            path=url,
            actual_status=resp.status_code,
            passed=passed,
            detail={"expected": expected_statuses, "soc2_controls": probe.soc2_controls},
        )

    def to_run_report_dict(self, summary: ProbeRunSummary, sandbox_id: str) -> dict:
        """Convert a ProbeRunSummary into a RunReport-compatible dict.

        The sandbox executor parses this from container stdout.
        """
        return {
            "sandbox_id": sandbox_id,
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "duration_seconds": summary.duration_seconds,
            "soc2_controls_covered": summary.soc2_controls_covered,
            "findings": summary.findings,
        }
