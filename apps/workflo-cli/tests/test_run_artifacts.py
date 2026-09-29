"""Exit-gate artifact materialization tests (Sprint 4 exit gate).

The run root must carry the full audit projection:
provenance.json, run_state.json (supervisor), observations.jsonl,
tool_calls.jsonl, evidence/, findings.json, agent_activity.json,
teardown_attestation.json, receipt.json, receipt.sig.
"""

import json
from datetime import UTC, datetime

from workflo_cli.run_artifacts import materialize_run_artifacts
from sandbox_isolation import generate_keypair
from workflo_schema.sandbox import (
    AgentActivity,
    CanaryCheckResult,
    RunReport,
    SignedReceipt,
    TeardownProof,
)


def _signed_receipt():
    receipt = SignedReceipt(
        sandbox_id="sbx-materialize",
        issued_at=datetime.now(UTC),
        run_report=RunReport(
            sandbox_id="sbx-materialize", run_id="sbx-materialize",
            total=3, passed=2, failed=1, duration_seconds=0.5,
            findings=[{
                "finding_id": "wf-fnd-" + "ab" * 8,
                "title": "POST /checkout fails (HTTP 500)",
                "severity": "medium",
                "status": "confirmed",
                "summary": "reproduced twice with healthy control",
                "evidence_refs": ["evt_1", "evt_2"],
                "reproduction": {"method": "POST", "url": "http://app.workflo.internal:3000/checkout",
                                 "observed_failures": 2, "failure_class": "5xx",
                                 "attempt_seqs": [1, 2]},
            }],
        ),
        teardown_proof=TeardownProof(
            sandbox_id="sbx-materialize", runtime_type="namespaces",
            container_removed=True, filesystem_removed=True,
            processes_terminated=True, cgroup_removed=True,
            network_namespace_removed=True, workspace_removed=True,
            no_snapshot_retained=True, destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="sbx-materialize", attempted_at=datetime.now(UTC),
            target_host="https://example.com", request_succeeded=False,
            error="blocked",
        ),
        agent_activity={
            "planner": "task_spec", "tool_calls": 5, "denied_attempts": 1,
            "steps_total": 5, "steps_completed": 4, "steps_failed": 1,
            "tools_used": ["http_get", "read_log", "list_files"],
        },
    )
    return generate_keypair().sign(receipt)


def _evidence(tmp_path):
    artifacts = tmp_path / "evidence" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "agent_tool_calls.jsonl").write_text(
        json.dumps({"seq": 1, "tool": "http_get", "denied": False, "ok": True,
                    "duration_ms": 4}) + "\n"
        + json.dumps({"seq": 2, "tool": "http_get", "denied": True, "ok": False,
                      "reason": "host not under .workflo.internal",
                      "duration_ms": 0}) + "\n"
    )
    (artifacts / "agent_report.json").write_text(json.dumps({
        "observations": [
            {"description": "checkout fails", "tool": "http_post", "ok": False,
             "denied": False, "detail": "HTTP 500"},
        ],
    }))
    return tmp_path / "evidence"


class TestMaterializeRunArtifacts:
    def test_full_exit_gate_set_written(self, tmp_path):
        evidence = _evidence(tmp_path)
        run_root = tmp_path / "run"
        receipt = _signed_receipt()

        written = materialize_run_artifacts(
            run_root, evidence, receipt=receipt, receipt_path=run_root / "receipt.json"
        )
        names = {p.name for p in run_root.iterdir()}
        expected = {
            "provenance.json", "observations.jsonl", "tool_calls.jsonl",
            "findings.json", "agent_activity.json", "teardown_attestation.json",
            "receipt.json", "receipt.sig", "artifacts_manifest.json",
        }
        assert expected <= names, f"missing: {expected - names}"
        assert str(run_root / "receipt.json") in written

        # receipt.sig matches the embedded signature
        sig_hex = (run_root / "receipt.sig").read_text().strip()
        assert sig_hex == receipt.signature

        # provenance carries the sandbox identity
        prov = json.loads((run_root / "provenance.json").read_text())
        assert prov["sandbox_id"] == "sbx-materialize"

        # findings projected from the receipt
        findings = json.loads((run_root / "findings.json").read_text())
        assert findings["findings"][0]["status"] == "confirmed"

        # teardown attestation carries all three components
        ta = json.loads((run_root / "teardown_attestation.json").read_text())
        assert ta["teardown_proof"]["network_namespace_removed"] is True
        assert ta["canary_check"]["request_succeeded"] is False

        # governed tool-call ledger copied verbatim
        lines = (run_root / "tool_calls.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["denied"] is True

        # observations JSONL from the agent report
        obs = (run_root / "observations.jsonl").read_text().strip().splitlines()
        assert json.loads(obs[0])["detail"] == "HTTP 500"

    def test_no_agent_tier_writes_empty_ledgers(self, tmp_path):
        evidence = _evidence(tmp_path)
        # No agent tier ran: neither the ledger nor the report exist.
        (evidence / "artifacts" / "agent_tool_calls.jsonl").unlink()
        (evidence / "artifacts" / "agent_report.json").unlink()
        receipt = _signed_receipt()
        payload = receipt.model_dump()
        payload["agent_activity"] = None
        receipt = SignedReceipt(**payload)
        generate_keypair().sign(receipt)

        run_root = tmp_path / "run2"
        materialize_run_artifacts(run_root, evidence, receipt=receipt)
        assert (run_root / "tool_calls.jsonl").read_text() == ""
        assert (run_root / "observations.jsonl").read_text() == ""
        assert not (run_root / "agent_activity.json").exists()

    def test_never_raises_without_receipt(self, tmp_path):
        written = materialize_run_artifacts(tmp_path / "run3", None, receipt=None)
        assert written == []

    def test_run_metrics_cost_rail_written(self, tmp_path):
        """run_metrics.json carries wall clock, agent usage, and the model
        cost rail (tokens + inference seconds) for benchmark math."""
        import json as _json

        receipt = _signed_receipt()
        payload = receipt.model_dump()
        payload["agent_activity"] = {
            "planner": "llm", "tool_calls": 3, "denied_attempts": 0,
            "steps_total": 3, "steps_completed": 3, "steps_failed": 0,
            "tools_used": ["http_get"],
            "inference_provenance": {
                "mode": "direct", "model": "qwen3-4b", "requests": 2,
                "input_tokens": 222, "output_tokens": 444,
                "inference_seconds": 1.5,
                "source_code_included": False,
            },
        }
        from workflo_schema.sandbox import SignedReceipt as _SR
        receipt = _SR(**payload)
        generate_keypair().sign(receipt)

        run_root = tmp_path / "run"
        (run_root).mkdir()
        (run_root / "run_state.json").write_text(_json.dumps({
            "sandbox_id": "sbx-materialize",
            "stages": {"preflight": "pass", "tests": "pass", "agent": "pass"},
        }))

        materialize_run_artifacts(
            run_root, tmp_path / "evidence", receipt=receipt,
            receipt_path=run_root / "receipt.json",
        )
        metrics = _json.loads((run_root / "run_metrics.json").read_text())
        assert metrics["sandbox_id"] == "sbx-materialize"
        assert metrics["wall_clock_seconds"] >= 0
        assert metrics["model"]["input_tokens"] == 222
        assert metrics["model"]["output_tokens"] == 444
        assert metrics["model"]["requests"] == 2
        assert metrics["model"]["inference_seconds"] == 1.5
        assert metrics["model"]["tokens_per_second"] == round((222 + 444) / 1.5, 3)
        assert metrics["agent"]["planner"] == "llm"
        assert metrics["stages"]["agent"] == "pass"
        assert metrics["findings_count"] == 1

    def test_run_metrics_model_null_without_llm(self, tmp_path):
        """task-spec runs (no model) record model: null — honest, not zero."""
        receipt = _signed_receipt()
        run_root = tmp_path / "run4"
        materialize_run_artifacts(run_root, tmp_path / "evidence",
                                  receipt=receipt)
        import json as _json
        metrics = _json.loads((run_root / "run_metrics.json").read_text())
        assert metrics["model"] is None
        assert metrics["agent"]["planner"] == "task_spec"
