from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import sandbox_isolation.verify_receipts as verifier

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_receipt_bundle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_receipt_bundle", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path) -> tuple[list[str], Path]:
    receipt = tmp_path / "receipt.json"
    public_key = tmp_path / "receipt-key.pub.pem"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    receipt.write_text("{}")
    public_key.write_text("public")
    (evidence / "manifest.json").write_text("{}")
    (evidence / "events.jsonl").write_text("{}\n")
    report = tmp_path / "verification.json"
    return [
        str(SCRIPT), "--receipt", str(receipt), "--pubkey", str(public_key),
        "--evidence", str(evidence), "--report", str(report),
    ], report


def test_release_verifier_retains_valid_metadata_only_outcome(monkeypatch, tmp_path):
    module = _load_module()
    args, report = _arguments(tmp_path)
    result = SimpleNamespace(
        status=SimpleNamespace(value="VALID"),
        checks_passed=["one", "two"],
        checks_failed=[],
    )
    monkeypatch.setattr(verifier, "verify_receipt", lambda *args, **kwargs: result)
    monkeypatch.setattr(sys, "argv", args)

    assert module.main() == 0
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is True
    assert evidence["status"] == "VALID"
    assert evidence["staging_secrets_present"] is False
    assert evidence["checks_passed_count"] == 2
    assert len(evidence["receipt_sha256"]) == 64


def test_release_verifier_rejects_inherited_staging_secret(monkeypatch, tmp_path):
    module = _load_module()
    args, report = _arguments(tmp_path)
    monkeypatch.setenv("WORKFLO_GATEWAY_API_KEY", "must-not-be-inherited")
    monkeypatch.setattr(sys, "argv", args)

    assert module.main() == 1
    evidence = json.loads(report.read_text())
    assert evidence["passed"] is False
    assert evidence["staging_secrets_present"] is True
    assert "must-not-be-inherited" not in report.read_text()
