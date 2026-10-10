from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "gateway_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gateway_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _provenance(*, redactions_applied: int = 0) -> dict:
    return {
        "source_code_included": False,
        "model": "frozen-model",
        "mode": "gateway",
        "request_ids": ["request-1"],
        "observation_sha256": "a" * 64,
        "prompt_sha256": "b" * 64,
        "response_sha256": "c" * 64,
        "input_tokens": 10,
        "output_tokens": 5,
        "inference_seconds": 0.02,
        "redactions_applied": redactions_applied,
    }


def test_gateway_smoke_checks_auth_privacy_redaction_and_provenance(
    monkeypatch, tmp_path
):
    module = _load_module()
    output = tmp_path / "gateway.json"
    responses = iter(
        [
            (401, {"detail": "unauthorized"}, 0.01),
            (403, {"detail": "forbidden"}, 0.01),
            (200, {"provenance": _provenance()}, 0.02),
            (200, {"provenance": _provenance(redactions_applied=1)}, 0.02),
            (422, {"detail": "unknown field"}, 0.01),
            (422, {"detail": "unknown field"}, 0.01),
            (422, {"detail": "source-bearing text"}, 0.01),
            (422, {"detail": "unknown field"}, 0.01),
        ]
    )

    monkeypatch.setattr(module, "post_json", lambda *args, **kwargs: next(responses))
    monkeypatch.setenv("WORKFLO_GATEWAY_BASE_URL", "https://gateway.example.invalid")
    monkeypatch.setenv("WORKFLO_GATEWAY_API_KEY", "secret")
    monkeypatch.setenv("WORKFLO_MODEL_NAME", "frozen-model")
    monkeypatch.setenv("WORKFLO_GATEWAY_SMOKE_OUT", str(output))

    assert module.main() == 0
    report = json.loads(output.read_text())
    assert report["passed"] is True
    assert report["authorization_rejection"]["passed"] is True
    assert report["wrong_key_rejection"]["passed"] is True
    assert report["source_rejection"]["passed"] is True
    assert report["source_rejection"]["cases"] == 4
    assert report["redaction"]["passed"] is True
    assert report["redaction"]["redactions_applied"] == 1
    assert report["valid_request"]["source_code_included"] is False

    serialized = output.read_text()
    assert "secret" not in serialized
    assert "WORKFLO-P4-SOURCE-CANARY" not in serialized
    assert "WFSECRET-P4" not in serialized
    assert "gateway.example.invalid" not in serialized


def test_gateway_smoke_retains_redacted_failure_report(monkeypatch, tmp_path):
    module = _load_module()
    output = tmp_path / "gateway.json"
    monkeypatch.setattr(
        module,
        "post_json",
        lambda *args, **kwargs: (200, {"detail": "unexpected"}, 0.01),
    )
    monkeypatch.setenv("WORKFLO_GATEWAY_BASE_URL", "https://gateway.example.invalid")
    monkeypatch.setenv("WORKFLO_GATEWAY_API_KEY", "secret")
    monkeypatch.setenv("WORKFLO_MODEL_NAME", "frozen-model")
    monkeypatch.setenv("WORKFLO_GATEWAY_SMOKE_OUT", str(output))

    assert module.main() == 1
    report = json.loads(output.read_text())
    assert report["passed"] is False
    assert report["failure_class"] == "missing_key_accepted"
    assert "secret" not in output.read_text()
    assert "gateway.example.invalid" not in output.read_text()
