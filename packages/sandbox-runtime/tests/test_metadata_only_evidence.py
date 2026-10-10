from __future__ import annotations

import json

from sandbox_runtime.evidence import EvidenceCollector, verify_evidence_bundle


def test_metadata_only_evidence_retains_hashes_not_payloads(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFLO_EVIDENCE_METADATA_ONLY", "1")
    evidence = EvidenceCollector(tmp_path / "evidence")
    secret = "source prompt and generated narrative must disappear"

    evidence.start()
    evidence.write_event("MODEL_OUTCOME", {"passed": True, "content": secret})
    evidence.write_artifact("model-output.txt", secret.encode())
    evidence.write_log("application", secret)
    evidence.stop()
    evidence.redact_retained_payloads()
    evidence.finalize([], "run-id", "sandbox-id")

    retained = "\n".join(
        path.read_text(errors="replace")
        for path in (tmp_path / "evidence").rglob("*")
        if path.is_file()
    )
    assert secret not in retained
    event = json.loads((tmp_path / "evidence" / "events.jsonl").read_text().splitlines()[1])
    assert event["data"]["passed"] is True
    assert len(event["data"]["content"]["sha256"]) == 64
    assert verify_evidence_bundle(tmp_path / "evidence") is True
