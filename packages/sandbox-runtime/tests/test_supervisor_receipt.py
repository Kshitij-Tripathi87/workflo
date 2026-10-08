"""End-to-end (mocked) supervisor lifecycle → unsigned receipt payload.

Exercises the vertical slice without Linux: every host-touching step
(bwrap, cgroups, netns, git) is patched, but the evidence ledger, the
teardown verification wiring, and the receipt payload construction run
for real.
"""

import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sandbox_runtime.config import RunConfig, DepMode
from sandbox_runtime.supervisor import Supervisor
from sandbox_runtime.evidence import verify_evidence_bundle
from sandbox_runtime.landlock import probe_abi

# Host kernel capability. The supervisor's policy DIFFERS by capability, so
# the security-mode tests below assert the branch this host is actually in
# rather than assuming Landlock is unavailable (which only held on kernels
# without Landlock and made the Linux gate fail).
LANDLOCK_ABI = probe_abi()


def _run_supervisor(supervisor, tmp_path, *, probe_stdout=None, probe_returncode=0):
    """Run a full (mocked) supervisor lifecycle and return the RunResult."""
    patches = _patch_lifecycle(
        tmp_path, probe_stdout=probe_stdout, probe_returncode=probe_returncode
    )
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        patches[2].return_value = MagicMock(
            mode=DepMode.VENDOR_CACHE, lockfile_sha256=None, cache_manifest_sha256=None
        )
        return asyncio.run(supervisor.run())


def _probe_report_json(*, canary_succeeded=False, critical_failures=()):
    """Build the JSON a sandbox probe process would emit."""
    probes = [
        {"name": "host_home_not_mounted", "passed": True, "detail": "ok", "severity": "critical"},
        {"name": "external_ipv4_blocked", "passed": True, "detail": "blocked", "severity": "critical"},
        {"name": "only_internal_routes_accessible", "passed": False, "detail": "app not started",
         "severity": "warning"},
    ]
    for name in critical_failures:
        probes.append({"name": name, "passed": False, "detail": "isolation broken", "severity": "critical"})
    return json.dumps({
        "probes": probes,
        "canary": {
            "target_host": "8.8.8.8:53",
            "request_succeeded": canary_succeeded,
            "error": None if canary_succeeded else "blocked",
        },
    }).encode()


def _fake_bwrap_proc(stdout=b"", returncode=0):
    proc = MagicMock()
    proc.poll.return_value = returncode
    proc.returncode = returncode
    proc.communicate.return_value = (stdout, b"")
    return proc


def _make_config(tmp_path, probe_groups=None):
    return RunConfig(
        sandbox_id="sbx-test-001",
        repo_path=tmp_path / "repo",
        probe_groups=probe_groups or ["surface"],
        runtime_image=tmp_path / "rootfs",
        memory_mb=1024,
        cpu_cores=1.0,
        timeout_seconds=60,
        dep_mode=DepMode.VENDOR_CACHE,
        evidence_dir=tmp_path / "runs",
    )


async def _noop(self):
    return None


async def _fake_test_workload(config, evidence):
    return {
        "proc": None,
        "pid": 123,
        "returncode": 0,
        "total": 3,
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "duration_seconds": 0.1,
        "collection_error": None,
    }


def _patch_lifecycle(tmp_path, *, probe_stdout=None, probe_returncode=0):
    """Patch every host-touching step of the supervisor lifecycle."""
    (tmp_path / "repo").mkdir(exist_ok=True)
    (tmp_path / "rootfs").mkdir(exist_ok=True)

    probe_proc = _fake_bwrap_proc(stdout=probe_stdout or _probe_report_json(), returncode=probe_returncode)

    return (
        patch.object(Supervisor, "_preflight", new=_noop),
        patch.object(Supervisor, "_snapshot_repo", new=_noop),
        patch("sandbox_runtime.supervisor.resolve_dependencies"),
        patch("sandbox_runtime.supervisor.prepare_rootfs"),
        patch("sandbox_runtime.supervisor.setup_cgroup", return_value=tmp_path / "cgroup" / "sbx"),
        patch("sandbox_runtime.supervisor.setup_private_network"),
        patch("sandbox_runtime.supervisor.attach_process"),
        patch("sandbox_runtime.supervisor.run_bwrap", return_value=probe_proc),
        patch("sandbox_runtime.supervisor.run_test_workload", side_effect=_fake_test_workload),
        # Teardown: netns check mocked True (no real netns on Windows)
        patch("sandbox_runtime.teardown.verify_network_namespace_removed", return_value=True),
    )


class TestSupervisorReceipt:
    def test_run_produces_unsigned_receipt_with_evidence_binding(self, tmp_path):
        config = _make_config(tmp_path)
        supervisor = Supervisor(config)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(supervisor, tmp_path)

        assert result.success is True, result.error
        assert result.teardown_verified is True
        assert result.receipt_payload is not None

        # The payload is SignedReceipt-compatible
        from workflo_schema.sandbox import SignedReceipt
        receipt = SignedReceipt(**result.receipt_payload)
        assert receipt.sandbox_id == "sbx-test-001"
        assert receipt.signature is None  # unsigned — CLI signs
        assert receipt.teardown_proof.runtime_type == "namespaces"
        assert receipt.teardown_proof.processes_terminated is True
        assert receipt.teardown_proof.cgroup_removed is True
        assert receipt.teardown_proof.network_namespace_removed is True
        assert receipt.teardown_proof.workspace_removed is True
        assert receipt.canary_check.request_succeeded is False  # egress blocked
        assert receipt.evidence_binding is not None

        # The evidence ledger verifies and its digests match the binding
        evidence_dir = tmp_path / "runs" / "sbx-test-001" / "evidence"
        assert verify_evidence_bundle(evidence_dir) is True
        assert receipt.evidence_binding.bundle_sha256 == json.loads(
            (evidence_dir / "manifest.json").read_text()
        )["bundle_sha256"]

        # Lifecycle events landed in the receipt with sandbox ids
        assert len(receipt.lifecycle_events) >= 5
        assert all(e.sandbox_id == "sbx-test-001" for e in receipt.lifecycle_events)

        # Writable state is gone; evidence survives
        assert not (tmp_path / "runs" / "sbx-test-001" / "workspace").exists()
        assert not (tmp_path / "runs" / "sbx-test-001" / "tmp").exists()
        assert (evidence_dir / "manifest.json").exists()

        # Unsigned receipt file was persisted next to the run root
        assert result.receipt_path is not None
        assert result.receipt_path.name == "receipt.unsigned.json"
        assert json.loads(result.receipt_path.read_text())["sandbox_id"] == "sbx-test-001"

    def test_tampered_evidence_fails_binding_verification(self, tmp_path):
        config = _make_config(tmp_path)
        supervisor = Supervisor(config)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(supervisor, tmp_path)

        assert result.success is True

        # Tamper with the evidence AFTER the run
        evidence_dir = tmp_path / "runs" / "sbx-test-001" / "evidence"
        events_file = evidence_dir / "events.jsonl"
        events_file.write_text(events_file.read_text() + '{"tampered": true}\n')

        assert verify_evidence_bundle(evidence_dir) is False

        from sandbox_isolation import verify_evidence_binding
        from workflo_schema.sandbox import SignedReceipt
        receipt = SignedReceipt(**result.receipt_payload)
        ok, checks = verify_evidence_binding(receipt, evidence_dir)
        assert ok is False

    def test_canary_success_fails_closed(self, tmp_path):
        """A canary that SUCCEEDED (isolation broken) must abort the run."""
        config = _make_config(tmp_path)
        supervisor = Supervisor(config)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(
            supervisor, tmp_path, probe_stdout=_probe_report_json(canary_succeeded=True)
        )

        assert result.success is False
        assert "canary" in (result.error or "").lower()

        # Failure receipt is STILL produced (and still unsigned for the CLI to sign)
        assert result.receipt_payload is not None
        from workflo_schema.sandbox import SignedReceipt
        receipt = SignedReceipt(**result.receipt_payload)
        assert receipt.canary_check.request_succeeded is True  # honestly recorded

    def test_probe_critical_failure_fails_closed(self, tmp_path):
        """A critical probe failure must abort the run before tests start."""
        config = _make_config(tmp_path)
        supervisor = Supervisor(config)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(
            supervisor, tmp_path,
            probe_stdout=_probe_report_json(critical_failures=("host_home_not_mounted_x",)),
        )

        assert result.success is False
        assert "Isolation verification failed" in (result.error or "")

    def test_emit_serializes_paths(self, tmp_path):
        """emit() must accept Path objects in config without crashing the ledger."""
        config = _make_config(tmp_path)
        supervisor = Supervisor(config)
        supervisor.emit("created", {"config": {"repo_path": Path("/some/path"), "nested": [Path("/x")]}})
        supervisor.emit("destroyed", {})

        events_file = tmp_path / "runs" / "sbx-test-001" / "evidence" / "events.jsonl"
        lines = events_file.read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["data"]["config"]["repo_path"] == "/some/path" or \
            "\\some\\path" in first["data"]["config"]["repo_path"]


class TestSecurityMode:
    """Phase 6 hardened/compatible policy (spec §5.3, F-1/F-5)."""

    def _make_supervisor(self, tmp_path, security_mode="compatible"):
        config = _make_config(tmp_path)
        config.security_mode = security_mode
        return Supervisor(config)

    def test_receipt_carries_security_attestation(self, tmp_path):
        """The receipt must attest what was ACTUALLY enforced."""
        supervisor = self._make_supervisor(tmp_path)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(supervisor, tmp_path)

        assert result.success is True, result.error
        attestation = result.receipt_payload["security_attestation"]
        assert attestation["security_mode"] == "compatible"
        assert attestation["cgroup_attached"] is True
        assert attestation["source_code_included"] is False
        # The attestation must SAY what the kernel probe found — never hide
        # reduced isolation.
        landlock = attestation["landlock"]
        if LANDLOCK_ABI > 0:
            # Landlock-capable kernel: the run requests it and records the ABI.
            assert landlock["requested"] is True
            assert landlock["abi_version"] == LANDLOCK_ABI
            # No in-sandbox status files in this mocked run => not "applied",
            # and the reason must be reported rather than left null.
            assert landlock["applied"] is False
            assert landlock["reason"] == "no_status_reported"
        else:
            # Unsupported kernel: compatible mode proceeds but says so.
            assert landlock["requested"] is False
            assert landlock["applied"] is False
            assert landlock["reason"] == "not_requested"

    def test_hardened_mode_landlock_policy(self, tmp_path):
        """hardened mode fails closed ONLY when Landlock is unavailable.

        Both directions are asserted so this is a real gate on a
        Landlock-capable kernel (where it must NOT refuse) and on kernels
        without Landlock (where it must abort before spawning workloads).
        """
        supervisor = self._make_supervisor(tmp_path, security_mode="hardened")
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(supervisor, tmp_path)

        if LANDLOCK_ABI > 0:
            assert result.success is True, result.error
            # The attestation must record the enforced posture.
            assert result.receipt_payload["security_attestation"]["landlock"]["requested"] is True
        else:
            assert result.success is False
            assert "Landlock" in (result.error or "")
            assert "hardened" in (result.error or "")
            # The failure is provable: a receipt is still produced
            assert result.receipt_payload is not None

    def test_cgroup_attach_failure_never_silent_compatible(self, tmp_path):
        """F-5: attach failure records evidence and reports reduced isolation."""
        supervisor = self._make_supervisor(tmp_path, security_mode="compatible")

        proc = _fake_bwrap_proc()
        with patch("sandbox_runtime.supervisor.attach_process",
                   side_effect=OSError(1, "no such cgroup")):
            supervisor.cgroup_path = tmp_path / "cgroup" / "sbx"
            supervisor.register_process("app", proc)

        assert "app" in supervisor._cgroup_attach_failures
        events = [e["event"] for e in supervisor.lifecycle_events]
        assert "CGROUP_ATTACH_FAILED" in events

    def test_cgroup_attach_failure_hardened_fails_closed(self, tmp_path):
        """F-5: hardened mode aborts when limits cannot be applied."""
        supervisor = self._make_supervisor(tmp_path, security_mode="hardened")

        proc = _fake_bwrap_proc()
        with patch("sandbox_runtime.supervisor.attach_process",
                   side_effect=OSError(1, "no such cgroup")):
            supervisor.cgroup_path = tmp_path / "cgroup" / "sbx"
            with pytest.raises(RuntimeError, match="hardened"):
                supervisor.register_process("app", proc)

    def test_no_cgroup_hardened_fails_closed(self, tmp_path):
        supervisor = self._make_supervisor(tmp_path, security_mode="hardened")
        with pytest.raises(RuntimeError, match="no cgroup"):
            supervisor.register_process("app", _fake_bwrap_proc())

    def test_landlock_posture_is_recorded_in_evidence(self, tmp_path):
        """The ledger records the REAL Landlock posture for this kernel."""
        supervisor = self._make_supervisor(tmp_path)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        result = _run_supervisor(supervisor, tmp_path)

        events = [e["event"] for e in result.lifecycle_events]
        if LANDLOCK_ABI > 0:
            assert "LANDLOCK_AVAILABLE" in events
            available = next(
                e for e in result.lifecycle_events if e["event"] == "LANDLOCK_AVAILABLE"
            )
            assert available["detail"]["abi"] == LANDLOCK_ABI
            assert available["detail"]["security_mode"] == "compatible"
            assert "LANDLOCK_UNAVAILABLE" not in events
        else:
            assert "LANDLOCK_UNAVAILABLE" in events
            assert "LANDLOCK_AVAILABLE" not in events

    def test_landlock_status_files_aggregate_into_attestation(self, tmp_path):
        """In-sandbox landlock-status-*.json -> receipt attestation."""
        supervisor = self._make_supervisor(tmp_path)
        supervisor.landlock_requested = True
        supervisor.landlock_abi = 3
        artifacts = supervisor.evidence.artifacts_dir
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "landlock-status-agent.json").write_text(json.dumps({
            "workload": "agent", "mode": "compatible", "abi": 3,
            "status": "LANDLOCK_APPLIED",
        }))
        (artifacts / "landlock-status-test.json").write_text(json.dumps({
            "workload": "test", "mode": "compatible", "abi": 3,
            "status": "LANDLOCK_APPLIED",
        }))

        applied, reason = supervisor._landlock_outcome()
        assert applied is True
        assert reason is None

    def test_one_failed_status_reduces_attestation(self, tmp_path):
        supervisor = self._make_supervisor(tmp_path)
        supervisor.landlock_requested = True
        supervisor.landlock_abi = 3
        artifacts = supervisor.evidence.artifacts_dir
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "landlock-status-agent.json").write_text(json.dumps({
            "workload": "agent", "abi": 3, "status": "LANDLOCK_APPLIED",
        }))
        (artifacts / "landlock-status-app.json").write_text(json.dumps({
            "workload": "app", "abi": 3, "status": "LANDLOCK_APPLY_FAILED",
        }))

        applied, reason = supervisor._landlock_outcome()
        assert applied is False
        assert reason == "LANDLOCK_APPLY_FAILED"

    def test_receipt_marks_completed_run(self, tmp_path):
        supervisor = self._make_supervisor(tmp_path)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)
        result = _run_supervisor(supervisor, tmp_path)
        assert result.success is True
        assert result.receipt_payload["run_status"] == "completed"
        assert "failure_stage" not in result.receipt_payload

    def test_failed_run_carries_stage(self, tmp_path):
        """Phase 7 contract: an aborted run still produces a signed receipt
        and it NAMES the stage that failed."""
        supervisor = self._make_supervisor(tmp_path)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)
        result = _run_supervisor(
            supervisor, tmp_path,
            probe_stdout=_probe_report_json(critical_failures=("host_home_not_mounted_x",)),
        )
        assert result.success is False
        assert result.receipt_payload["run_status"] == "failed"
        assert result.receipt_payload["failure_stage"] == "probes"


# ---------------------------------------------------------------------------

def _agent_record(seq, tool, url, status):
    """A governed tool record as agent_tool_calls.jsonl would carry it."""
    return {
        "seq": seq,
        "tool": tool,
        "args": {"url": url},
        "denied": False,
        "ok": True,
        "duration_ms": 12,
        "result_summary": {"ok": True, "status": status},
    }


async def _fake_agent_workload(config, evidence):
    """Simulated agent run: app root healthy, /checkout fails twice."""
    records = [
        _agent_record(1, "http_get", "http://app.workflo.internal:3000/", 200),
        _agent_record(2, "http_post", "http://app.workflo.internal:3000/checkout", 500),
        _agent_record(3, "http_post", "http://app.workflo.internal:3000/checkout", 500),
    ]
    # Persist the records file the way the real agent sandbox does — the
    # supervisor path under test reads it for both ledger and judge.
    records_path = evidence.artifacts_dir / "agent_tool_calls.jsonl"
    records_path.parent.mkdir(parents=True, exist_ok=True)
    with open(records_path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    report_path = evidence.artifacts_dir / "agent_report.json"
    report_path.write_text(json.dumps({
        "task_id": config.sandbox_id,
        "mode": "planner",
        "steps_total": 3,
        "steps_completed": 1,
        "steps_failed": 2,
        "tool_calls": 3,
        "denied_attempts": 0,
        "errors": 0,
        "tools_used": ["http_get", "http_post"],
    }))
    return {
        "proc": None,
        "pid": 4242,
        "returncode": 0,
        "activity": {
            "tool_calls": 3,
            "tools_used": ["http_get", "http_post"],
            "steps_total": 3,
            "steps_completed": 1,
            "steps_failed": 2,
            "denied_attempts": 0,
            "errors": 0,
            "planner": "llm",
        },
        "records": records,
        "records_full": records,
        "planner_enabled": True,
        "planner_events": [],
    }


class TestJudgeIntegration:
    """Day 10/11: governed records -> Judge -> findings on the receipt."""

    def test_reproduced_failure_becomes_confirmed_finding(self, tmp_path):
        config = _make_config(tmp_path, probe_groups=["deep"])
        supervisor = Supervisor(config)
        (tmp_path / "cgroup" / "sbx").mkdir(parents=True)

        async def _fake_app(config, evidence):
            return {"proc": None, "app_log_path": None, "app_log": None}

        patches = _patch_lifecycle(tmp_path)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            mocks[2].return_value = MagicMock(
                mode=DepMode.VENDOR_CACHE, lockfile_sha256=None,
                cache_manifest_sha256=None,
            )
            stack.enter_context(patch(
                "sandbox_runtime.supervisor.run_app_workload",
                side_effect=_fake_app,
            ))
            stack.enter_context(patch(
                "sandbox_runtime.supervisor.run_agent_workload",
                side_effect=_fake_agent_workload,
            ))
            result = asyncio.run(supervisor.run())

        assert result.success is True, result.error
        payload = result.receipt_payload
        assert payload["agent_activity"]["planner"] == "llm"

        findings = payload["run_report"]["findings"]
        assert len(findings) == 1
        finding = findings[0]
        assert finding["status"] == "confirmed"
        assert "checkout" in finding["title"]
        # Evidence refs must be real ledger event ids (evt_*) — the judge
        # ran AFTER the records were ingested into the hash-chained ledger.
        assert all(ref.startswith("evt_") for ref in finding["evidence_refs"])

        # The judged event left a mark in the lifecycle trail.
        events = [e["event"] for e in result.lifecycle_events]
        assert "FINDINGS_JUDGED" in events

        # And the whole payload still fits the signed schema.
        from workflo_schema.sandbox import SignedReceipt
        receipt = SignedReceipt(**payload)
        assert receipt.run_report.findings[0]["status"] == "confirmed"
