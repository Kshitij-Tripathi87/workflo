from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from click.testing import CliRunner
from workflo_cli.main import cli
from workflo_schema.sandbox import (
    CanaryCheckResult,
    LocalModelProvenance,
    RunReport,
    SignedReceipt,
    TeardownProof,
)


def _receipt(tmp_path, teardown: bool, error: str | None = None):
    receipt = SignedReceipt(
        sandbox_id="local-model-verify",
        issued_at=datetime.now(UTC),
        run_report=RunReport(sandbox_id="local-model-verify", total=1, passed=1),
        teardown_proof=TeardownProof(
            sandbox_id="local-model-verify",
            container_removed=True,
            filesystem_removed=True,
            model_inference_teardown=teardown,
            destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="local-model-verify",
            attempted_at=datetime.now(UTC),
            request_succeeded=False,
        ),
        local_model_provenance=LocalModelProvenance(
            model="qwen-local",
            server_image="image@sha256:" + "a" * 64,
            base_model_sha256="b" * 64,
            adapter_sha256={
                "test-gen": "c" * 64,
                "reasoning": "d" * 64,
                "reporting": "e" * 64,
            },
            requests=1,
            inference_seconds=0.5,
            error=error,
        ),
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(receipt.model_dump_json())
    key_path = tmp_path / "key.pem"
    key_path.write_text("mock")
    return receipt_path, key_path


def test_verify_accepts_clean_local_model_provenance(tmp_path):
    runner = CliRunner()
    receipt, key = _receipt(tmp_path, teardown=True)
    with patch("workflo_cli.main._load_ed25519_pubkey"), patch(
        "workflo_cli.main.verify_receipt_signature", return_value=True
    ):
        result = runner.invoke(
            cli, ["verify", "--receipt", str(receipt), "--pubkey", str(key)]
        )
    assert result.exit_code == 0, result.output
    assert "pinned local llama.cpp provenance" in result.output


def test_verify_rejects_local_model_without_teardown(tmp_path):
    runner = CliRunner()
    receipt, key = _receipt(tmp_path, teardown=False)
    with patch("workflo_cli.main._load_ed25519_pubkey"), patch(
        "workflo_cli.main.verify_receipt_signature", return_value=True
    ):
        result = runner.invoke(
            cli, ["verify", "--receipt", str(receipt), "--pubkey", str(key)]
        )
    assert result.exit_code != 0
    assert "model process/state teardown was not verified" in result.output


def test_verify_rejects_signed_local_model_error(tmp_path):
    runner = CliRunner()
    receipt, key = _receipt(tmp_path, teardown=True, error="adapter unavailable")
    with patch("workflo_cli.main._load_ed25519_pubkey"), patch(
        "workflo_cli.main.verify_receipt_signature", return_value=True
    ):
        result = runner.invoke(
            cli, ["verify", "--receipt", str(receipt), "--pubkey", str(key)]
        )
    assert result.exit_code != 0
    assert "records an inference error" in result.output
