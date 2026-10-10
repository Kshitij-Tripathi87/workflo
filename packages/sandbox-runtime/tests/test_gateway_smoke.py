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


def test_gateway_smoke_checks_auth_privacy_and_provenance(monkeypatch, tmp_path):
    module = _load_module()
    output = tmp_path / "gateway.json"
    responses = iter(
        [
            (401, {"detail": "unauthorized"}, 0.01),
            (
                200,
                {
                    "provenance": {
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
                    }
                },
                0.02,
            ),
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
    assert report["authorization_rejection"]["passed"] is True
    assert report["source_rejection"]["passed"] is True
    assert report["valid_request"]["source_code_included"] is False
    assert "secret" not in output.read_text()
    assert "WORKFLO_P4_SOURCE_CANARY_DO_NOT_FORWARD" not in output.read_text()
