from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    path = ROOT / "scripts" / "release" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def test_cost_summary_uses_explicit_rate_and_completed_requests(monkeypatch, tmp_path):
    module, script = _load("summarize_benchmark_cost.py")
    paths = []
    for repeat in range(3):
        path = tmp_path / f"benchmark-{repeat}.json"
        path.write_text(json.dumps({
            "assumptions": {"instance_hourly_usd": 3.6},
            "levels": [
                {"wall_seconds": 10.0, "succeeded": 10, "requests": 10, "failed": 0}
            ],
        }))
        paths.append(path)
    output = tmp_path / "cost.json"
    argv = [str(script)]
    for path in paths:
        argv.extend(("--benchmark", str(path)))
    argv.extend((
        "--instance-hourly-usd", "3.6", "--representative-requests", "3",
        "--out", str(output),
    ))
    monkeypatch.setattr(sys, "argv", argv)

    assert module.main() == 0
    report = json.loads(output.read_text())
    assert report["passed"] is True
    assert report["requests_completed"] == 30
    assert report["estimated_cost_per_request_usd"] == 0.001
    assert report["estimated_cost_per_representative_run_usd"] == 0.003


def test_safe_failure_reducer_discards_narrative_and_credentials(monkeypatch, tmp_path):
    module, script = _load("assert_safe_failure.py")
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({
        "endpoint_sha256": "a" * 64,
        "model": "frozen-model",
        "levels": [{
            "concurrency": 1,
            "requests": 1,
            "succeeded": 0,
            "failed": 1,
            "wall_seconds": 0.1,
            "errors": ["transport_URLError"],
        }],
        "unsafe_unused_field": "credential-bearing narrative",
    }))
    output = tmp_path / "failure.json"
    monkeypatch.setattr(sys, "argv", [
        str(script), "--raw", str(raw), "--command-exit-code", "1",
        "--out", str(output),
    ])

    assert module.main() == 0
    retained = output.read_text()
    report = json.loads(retained)
    assert report["passed"] is True
    assert report["error_classes"] == ["transport_URLError"]
    assert "credential-bearing narrative" not in retained


def test_evidence_scan_rejects_secret_without_retaining_it(monkeypatch, tmp_path):
    module, script = _load("scan_p4_evidence.py")
    for relative in module.REQUIRED_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")
    secret = "p4-secret-value-that-must-not-survive"
    (tmp_path / "gateway-smoke.json").write_text(secret)
    output = tmp_path / "redaction-check.json"
    monkeypatch.setenv("WORKFLO_GATEWAY_API_KEY", secret)
    monkeypatch.setattr(sys, "argv", [
        str(script), "--root", str(tmp_path),
        "--secret-env", "WORKFLO_GATEWAY_API_KEY", "--out", str(output),
    ])

    assert module.main() == 1
    retained = output.read_text()
    report = json.loads(retained)
    assert report["passed"] is False
    assert report["staging_secrets_present"] is True
    assert "gateway-smoke.json" in report["rejected_files"]
    assert secret not in retained

    (tmp_path / "gateway-smoke.json").write_text("{}\n")
    monkeypatch.delenv("WORKFLO_GATEWAY_API_KEY")
    assert module.main() == 0
    assert json.loads(output.read_text())["passed"] is True


def test_independent_verification_job_has_no_environment_or_staging_secrets():
    workflow = (ROOT / ".github/workflows/p4-model-acceptance.yml").read_text()
    independent = workflow.split("  independent-verification:\n", 1)[1]

    assert "runs-on: ubuntu-latest" in independent
    assert "actions/download-artifact@v4" in independent
    assert "environment:" not in independent
    assert "secrets." not in independent
    assert "--tamper-checks" in independent
    assert "--phase final" in independent


def test_teardown_report_requires_all_processes_and_containers_absent(
    monkeypatch, tmp_path
):
    module, script = _load("verify_p4_teardown.py")
    monkeypatch.setattr(module, "_container_absent", lambda _name: True)
    monkeypatch.setattr(module, "_process_counts", lambda: (0, 0, 0))
    monkeypatch.setattr(
        module,
        "_run",
        lambda _command: SimpleNamespace(returncode=0, stdout="State Recv-Q Send-Q\n"),
    )
    output = tmp_path / "teardown.json"
    monkeypatch.setattr(sys, "argv", [
        str(script), "--candidate", "candidate", "--rollback", "rollback",
        "--out", str(output),
    ])

    assert module.main() == 0
    report = json.loads(output.read_text())
    assert report["passed"] is True
    assert report["model_listener_count"] == 0
    assert report["unexpected_cache_count"] == 0
