"""Tests for evidence binding verification (outside-verifier side)."""

import json
from pathlib import Path

from sandbox_isolation.evidence_binding import (
    compute_evidence_digests,
    verify_evidence_binding,
    resolve_evidence_dir,
)


def _build_evidence(tmp_path: Path, sandbox_id: str = "sbx-1") -> Path:
    """Create a real evidence bundle via the runtime's collector."""
    from sandbox_runtime.evidence import EvidenceCollector

    evidence_dir = tmp_path / "runs" / sandbox_id / "evidence"
    collector = EvidenceCollector(evidence_dir)
    collector.write_event("created", {"sandbox_id": sandbox_id})
    collector.write_event("destroyed", {"teardown_verified": True})
    collector.write_artifact("test_stdout.txt", b"3 passed")
    collector.finalize([], sandbox_id, sandbox_id)
    return evidence_dir


def _build_receipt_with_binding(sandbox_id: str, evidence_dir: Path):
    from workflo_schema.sandbox import SignedReceipt
    from sandbox_runtime.evidence import EvidenceCollector

    collector = EvidenceCollector(evidence_dir)
    binding = collector.build_binding()
    return SignedReceipt(
        sandbox_id=sandbox_id,
        issued_at="2026-09-13T00:00:00Z",
        run_report={"sandbox_id": sandbox_id, "total": 3, "passed": 3},
        teardown_proof={
            "sandbox_id": sandbox_id,
            "runtime_type": "namespaces",
            "destroyed_at": "2026-09-13T00:01:00Z",
            "processes_terminated": True,
            "cgroup_removed": True,
            "network_namespace_removed": True,
            "workspace_removed": True,
            "container_removed": True,
            "filesystem_removed": True,
        },
        canary_check={
            "sandbox_id": sandbox_id,
            "attempted_at": "2026-09-13T00:00:30Z",
            "target_host": "8.8.8.8:53",
            "request_succeeded": False,
            "error": "blocked",
        },
        evidence_binding=binding,
    )


class TestComputeEvidenceDigests:
    def test_recomputes_all_digests(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        digests = compute_evidence_digests(evidence_dir)

        manifest = json.loads((evidence_dir / "manifest.json").read_text())
        assert digests is not None
        assert digests["events_count"] == manifest["events_count"]
        assert digests["events_sha256"] == manifest["events_sha256"]
        assert digests["bundle_sha256"] == manifest["bundle_sha256"]

    def test_missing_manifest_returns_none(self, tmp_path):
        assert compute_evidence_digests(tmp_path) is None

    def test_broken_chain_returns_none(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        events = evidence_dir / "events.jsonl"
        # Tamper: append a forged event
        events.write_text(events.read_text() + json.dumps({
            "event_id": "evt_00000099", "timestamp": "2026-01-01T00:00:00Z",
            "event_type": "FORGED", "data": {}, "prev_hash": "0" * 64,
            "event_hash": "f" * 64,
        }) + "\n")
        assert compute_evidence_digests(evidence_dir) is None


class TestVerifyEvidenceBinding:
    def test_matching_binding_passes(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)

        ok, checks = verify_evidence_binding(receipt, evidence_dir)
        assert ok is True, checks
        assert any("OK" in c for c in checks)

    def test_tampered_events_fail(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)

        # Tamper AFTER the binding was computed
        events = evidence_dir / "events.jsonl"
        lines = events.read_text().splitlines()
        forged = json.loads(lines[0])
        forged["data"] = {"sneaky": "payload"}
        lines[0] = json.dumps(forged)
        events.write_text("\n".join(lines) + "\n")

        ok, checks = verify_evidence_binding(receipt, evidence_dir)
        assert ok is False

    def test_extra_artifact_fails_bundle_digest(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)

        # Sneak an extra artifact in after finalization
        (evidence_dir / "artifacts" / "injected.txt").write_text("not from this run")

        ok, checks = verify_evidence_binding(receipt, evidence_dir)
        assert ok is False

    def test_missing_binding_fails(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)
        receipt.evidence_binding = None

        ok, checks = verify_evidence_binding(receipt, evidence_dir)
        assert ok is False

    def test_missing_evidence_dir_fails(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)

        ok, checks = verify_evidence_binding(receipt, tmp_path / "nope")
        assert ok is False


class TestResolveEvidenceDir:
    def test_absolute_path_resolves(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)

        assert resolve_evidence_dir(tmp_path / "receipt.json", receipt) == evidence_dir

    def test_sibling_layout_resolves(self, tmp_path):
        """Receipt in <run_root>/receipt.json, evidence in <run_root>/evidence."""
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)
        # Binding path points somewhere that no longer exists (e.g. the
        # evidence was moved next to the receipt)
        receipt.evidence_binding.evidence_dir = "/moved/elsewhere"
        receipt_path = evidence_dir.parent / "receipt.json"
        receipt_path.write_text("{}")

        assert resolve_evidence_dir(receipt_path, receipt) == evidence_dir

    def test_unresolvable_returns_none(self, tmp_path):
        evidence_dir = _build_evidence(tmp_path)
        receipt = _build_receipt_with_binding("sbx-1", evidence_dir)
        receipt.evidence_binding.evidence_dir = "/gone"
        receipt.evidence_binding = receipt.evidence_binding.model_copy(
            update={"evidence_dir": "/gone"}
        )

        assert resolve_evidence_dir(tmp_path / "receipt.json", receipt) is None
