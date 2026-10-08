"""E2E runner test — the full pipeline as a black box.

Runs `scripts/e2e_run.py --demo` as a subprocess (the most honest way to
test the run contract: no imports, no mocks of our own code) and asserts:

  * exit 0 (receipt signed AND self-verified)
  * a confirmed finding for the fixture's broken /checkout
  * the run_state.json console snapshot exists and shows completion
  * the signed receipt independently verifies via the real signer API
  * the workspace was actually torn down (teardown claims are real)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "e2e_run.py"


def _run_demo(out_dir: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--demo",
           "--instruction", "Test health and checkout",
           "--out", str(out_dir)] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("e2e")
    result = _run_demo(out)
    return out, result


class TestDemoEndToEnd:
    def test_exits_zero(self, demo_run):
        out, result = demo_run
        assert result.returncode == 0, (
            f"e2e failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

    def test_confirmed_finding_reported(self, demo_run):
        out, result = demo_run
        assert "[finding:confirmed]" in result.stdout
        assert "/checkout" in result.stdout

    def test_receipt_signed_and_independently_verified(self, demo_run):
        out, _ = demo_run
        receipt_path = out / "receipt.json"
        key_path = out / "receipt-key.pub.pem"
        assert receipt_path.exists() and key_path.exists()

        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat, load_pem_public_key,
        )
        from sandbox_isolation import verify_receipt_signature
        from workflo_schema.sandbox import SignedReceipt

        receipt = SignedReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8"))
        pub = load_pem_public_key(key_path.read_bytes())
        assert verify_receipt_signature(receipt, pub) is True

    def test_mission_and_provenance_in_signed_payload(self, demo_run):
        out, _ = demo_run
        from workflo_schema.sandbox import SignedReceipt

        receipt = SignedReceipt.model_validate_json(
            (out / "receipt.json").read_text(encoding="utf-8"))
        assert receipt.agent_activity is not None
        assert receipt.agent_activity.mission == "Test health and checkout"
        assert receipt.repository is not None
        assert len(receipt.repository.commit) == 40
        assert receipt.run_report.findings[0]["status"] == "confirmed"

    def test_run_state_console_snapshot(self, demo_run):
        out, _ = demo_run
        state_files = list(out.glob("runs/*/run_state.json"))
        assert state_files, "run_state.json missing"
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        assert state["status"] == "completed"
        assert state["stages"]["receipt"] == "pass"
        assert state["findings"]["confirmed"] == 1
        # Honest console: kernel-isolation stages stay unexercised here —
        # they belong to the Linux supervisor path, not the dev harness.
        assert "isolation" not in state["stages"]

    def test_workspace_torn_down_by_default(self, demo_run):
        out, _ = demo_run
        workspaces = list(out.glob("runs/*/workspace"))
        assert workspaces == []

    def test_keep_workspace_flag_retains_clone(self, tmp_path):
        out = tmp_path / "keep"
        result = _run_demo(out, extra=["--keep-workspace"])
        assert result.returncode == 0
        workspaces = list(out.glob("runs/*/workspace/repo"))
        assert workspaces, "--keep-workspace should retain the clone"
