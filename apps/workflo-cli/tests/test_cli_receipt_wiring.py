"""End-to-end vertical slice test: run -> sign -> receipt -> verify.

Exercises the complete product loop with everything real except the
Linux sandbox itself (mocked supervisor):

    workflo run --repo <url> --test
        -> supervisor (mocked) returns unsigned payload + evidence bundle
        -> CLI signs it with a fresh Ed25519 key
        -> receipt.json persisted next to the evidence

    workflo verify receipt.json
        -> schema check
        -> key resolution (local key store)
        -> Ed25519 signature verification
        -> namespace teardown claims
        -> canary claim
        -> evidence binding recomputed from the ledger
        -> VERIFIED (exit 0)

Plus tamper detection in both directions: tampering the receipt breaks
the signature; tampering the evidence breaks the binding.
"""

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from workflo_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Isolate Path.home() so key persistence never touches the real user."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


@pytest.fixture
def clean_llm_config(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFLO_CONFIG_DIR", str(tmp_path))
    from workflo_cli import llm_config
    yield llm_config
    llm_config.clear_llm_config()


def _make_run_result_with_evidence(sandbox_id: str, tmp_path: Path):
    """Supervisor-style RunResult with a REAL evidence bundle."""
    from sandbox_runtime.config import RunResult
    from sandbox_runtime.evidence import EvidenceCollector

    run_root = tmp_path / "runs" / sandbox_id
    evidence_dir = run_root / "evidence"
    collector = EvidenceCollector(evidence_dir)
    collector.write_event("created", {"sandbox_id": sandbox_id})
    collector.write_event("probes_passed", {"count": 15, "canary_blocked": True})
    collector.write_event("tests_completed", {"total": 3, "passed": 3})
    collector.write_event("destroyed", {"teardown_verified": True})
    collector.finalize([], sandbox_id, sandbox_id)
    binding = collector.build_binding()

    payload = {
        "sandbox_id": sandbox_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "run_report": {
            "sandbox_id": sandbox_id,
            "total": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
        },
        "teardown_proof": {
            "sandbox_id": sandbox_id,
            "destroyed_at": datetime.now(UTC).isoformat(),
            "runtime_type": "namespaces",
            "filesystem_wipe_method": "workspace_rmtree",
            "container_removed": True,
            "filesystem_removed": True,
            "no_snapshot_retained": True,
            "processes_terminated": True,
            "cgroup_removed": True,
            "network_namespace_removed": True,
            "workspace_removed": True,
        },
        "canary_check": {
            "sandbox_id": sandbox_id,
            "attempted_at": datetime.now(UTC).isoformat(),
            "target_host": "8.8.8.8:53",
            "request_succeeded": False,
            "error": "ConnectionRefusedError: blocked",
        },
        "lifecycle_events": [
            {"sandbox_id": sandbox_id, "event": "created",
             "timestamp": datetime.now(UTC).isoformat(), "detail": {}},
            {"sandbox_id": sandbox_id, "event": "destroyed",
             "timestamp": datetime.now(UTC).isoformat(), "detail": {}},
            {"sandbox_id": sandbox_id, "event": "receipt_built",
             "timestamp": datetime.now(UTC).isoformat(), "detail": {}},
        ],
        "evidence_binding": binding,
        "signature_algorithm": "ed25519",
    }
    return RunResult(
        sandbox_id=sandbox_id,
        success=True,
        receipt_payload=payload,
        evidence_dir=evidence_dir,
        teardown_verified=True,
        elapsed_seconds=1.25,
        lifecycle_events=[],
    )


class TestVerticalSlice:
    def test_run_signs_and_verify_passes(
        self, runner, tmp_path, isolated_home, clean_llm_config
    ):
        sandbox_id = "sbx-e2e-001"
        fake_result = _make_run_result_with_evidence(sandbox_id, tmp_path)
        client = MagicMock()
        client.run.return_value = fake_result

        with patch("workflo_cli.main.create_supervisor_client", return_value=client), \
             patch("workflo_cli.main.generate_sandbox_id", return_value=sandbox_id):
            run_result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test",
            ])

        assert run_result.exit_code == 0, f"{run_result.output}\n{run_result.exception}"
        assert "Signed receipt:" in run_result.output

        # The signed receipt exists next to the evidence bundle
        receipt_path = tmp_path / "runs" / sandbox_id / "receipt.json"
        assert receipt_path.exists()
        receipt_data = json.loads(receipt_path.read_text())
        assert receipt_data["signature"]  # signed
        assert receipt_data["public_key_fingerprint"]

        # The public key was persisted for offline verification
        key_file = (
            isolated_home / ".config" / "workflo" / "keys"
            / f"{receipt_data['public_key_fingerprint']}.pub.pem"
        )
        assert key_file.exists()

        # --- workflo verify: the second half of the product loop ---
        verify_result = runner.invoke(cli, ["verify", "--receipt", str(receipt_path)])

        assert verify_result.exit_code == 0, f"{verify_result.output}\n{verify_result.exception}"
        assert "signature verified" in verify_result.output
        assert "namespace teardown verified" in verify_result.output
        assert "canary confirms egress was blocked" in verify_result.output
        assert "evidence bundle verified" in verify_result.output

    def test_verify_detects_receipt_tampering(
        self, runner, tmp_path, isolated_home, clean_llm_config
    ):
        sandbox_id = "sbx-e2e-002"
        fake_result = _make_run_result_with_evidence(sandbox_id, tmp_path)
        client = MagicMock()
        client.run.return_value = fake_result

        with patch("workflo_cli.main.create_supervisor_client", return_value=client), \
             patch("workflo_cli.main.generate_sandbox_id", return_value=sandbox_id):
            runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test",
            ])

        receipt_path = tmp_path / "runs" / sandbox_id / "receipt.json"
        assert receipt_path.exists()

        # Tamper: inflate the pass count inside the signed payload
        data = json.loads(receipt_path.read_text())
        data["run_report"]["passed"] = 999
        receipt_path.write_text(json.dumps(data))

        verify_result = runner.invoke(cli, ["verify", "--receipt", str(receipt_path)])
        assert verify_result.exit_code == 1
        assert "signature verification failed" in verify_result.output

    def test_verify_detects_evidence_tampering(
        self, runner, tmp_path, isolated_home, clean_llm_config
    ):
        sandbox_id = "sbx-e2e-003"
        fake_result = _make_run_result_with_evidence(sandbox_id, tmp_path)
        client = MagicMock()
        client.run.return_value = fake_result

        with patch("workflo_cli.main.create_supervisor_client", return_value=client), \
             patch("workflo_cli.main.generate_sandbox_id", return_value=sandbox_id):
            runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test",
            ])

        receipt_path = tmp_path / "runs" / sandbox_id / "receipt.json"

        # Tamper the EVIDENCE (not the receipt): forge an event into the ledger
        events_file = tmp_path / "runs" / sandbox_id / "evidence" / "events.jsonl"
        events_file.write_text(events_file.read_text() + json.dumps({
            "event_id": "evt_00000099", "timestamp": "2026-01-01T00:00:00Z",
            "event_type": "FORGED", "data": {}, "prev_hash": "0" * 64,
            "event_hash": "f" * 64,
        }) + "\n")

        verify_result = runner.invoke(cli, ["verify", "--receipt", str(receipt_path)])
        # Signature still passes, but the binding must fail
        assert verify_result.exit_code == 1
        assert "evidence binding verification failed" in verify_result.output

    def test_verify_rejects_broken_teardown_claims(
        self, runner, tmp_path, isolated_home, clean_llm_config
    ):
        sandbox_id = "sbx-e2e-004"
        fake_result = _make_run_result_with_evidence(sandbox_id, tmp_path)
        # Break the teardown claim: cgroup survived
        fake_result.receipt_payload["teardown_proof"]["cgroup_removed"] = False
        fake_result.receipt_payload["teardown_proof"]["container_removed"] = False
        client = MagicMock()
        client.run.return_value = fake_result

        with patch("workflo_cli.main.create_supervisor_client", return_value=client), \
             patch("workflo_cli.main.generate_sandbox_id", return_value=sandbox_id):
            runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test",
            ])

        receipt_path = tmp_path / "runs" / sandbox_id / "receipt.json"

        verify_result = runner.invoke(cli, ["verify", "--receipt", str(receipt_path)])
        assert verify_result.exit_code == 1
        assert "cgroup_removed" in verify_result.output
