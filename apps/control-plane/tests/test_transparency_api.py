"""Transparency-log control-plane wiring tests (SOC 2 CC6.8/CC7.2).

End-to-end: a completed run appends its receipt fingerprint to the
append-only Merkle log; GET /v1/runs/{id}/proof (project-scoped) returns
an inclusion proof that verifies OFFLINE against the pinned root.
"""

import json
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings


def _real_signed_receipt_json() -> str:
    """A cryptographically valid SandboxRunResult.to_json() stand-in."""
    from sandbox_isolation import generate_keypair
    from workflo_schema.sandbox import (
        CanaryCheckResult,
        RunReport,
        SandboxLifecycleEvent,
        SignedReceipt,
        TeardownProof,
    )

    receipt = SignedReceipt(
        sandbox_id="sb-transparency",
        issued_at=datetime.now(UTC),
        run_report=RunReport(
            sandbox_id="sb-transparency", total=3, passed=3, failed=0,
            duration_seconds=1.0,
        ),
        teardown_proof=TeardownProof(
            sandbox_id="sb-transparency", container_id="c1",
            container_removed=True, filesystem_removed=True,
            no_snapshot_retained=True, destroyed_at=datetime.now(UTC),
        ),
        canary_check=CanaryCheckResult(
            sandbox_id="sb-transparency", attempted_at=datetime.now(UTC),
            target_host="https://example.com", request_succeeded=False,
            error="blocked",
        ),
        lifecycle_events=[
            SandboxLifecycleEvent(sandbox_id="sb-transparency", event=e,
                                  timestamp=datetime.now(UTC))
            for e in ("created", "destroyed", "receipt_signed")
        ],
    )
    generate_keypair().sign(receipt)
    return json.dumps({
        "success": True,
        "receipt": receipt.model_dump(mode="json"),
        "report": receipt.run_report.model_dump(mode="json"),
        "lifecycle_events": [],
        "elapsed_seconds": 1.0,
        "error": None,
    })


def _demo_headers(client):
    resp = client.post("/v1/auth/demo-token")
    return {"X-API-Key": resp.json()["api_key"]}


def _wait_terminal(client, run_id, headers, attempts=60):
    for _ in range(attempts):
        resp = client.get(f"/v1/runs/{run_id}", headers=headers)
        if resp.json()["status"] in ("completed", "failed"):
            return resp.json()
        time.sleep(0.05)
    raise AssertionError("run never reached terminal state")


class TestTransparencyWiring:
    def test_completed_run_appends_and_proves_inclusion(self, client, tmp_path, monkeypatch):
        log_path = tmp_path / "transparency.log"
        monkeypatch.setattr(settings, "transparency_log_path", str(log_path))
        headers = _demo_headers(client)

        with patch("workflo_executor.SandboxExecutor") as mock_cls:
            result = MagicMock()
            result.to_json.return_value = _real_signed_receipt_json()
            mock_cls.return_value.run.return_value = result

            resp = client.post(
                "/v1/runs",
                json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
                headers=headers,
            )
            run_id = resp.json()["run_id"]
            data = _wait_terminal(client, run_id, headers)

        assert data["status"] == "completed"
        assert log_path.exists(), "completed run must append to the log"

        # The endpoint returns a proof; verify it offline against the root.
        proof_resp = client.get(f"/v1/runs/{run_id}/proof", headers=headers)
        assert proof_resp.status_code == 200, proof_resp.text
        proof = proof_resp.json()

        from sandbox_isolation.transparency import verify_inclusion
        from workflo_schema.sandbox import SignedReceipt
        from sandbox_isolation import receipt_fingerprint

        receipt = SignedReceipt(**data["receipt"]["receipt"])
        leaf = receipt_fingerprint(receipt.canonical_payload())
        assert verify_inclusion(
            leaf, proof["leaf_index"], proof["tree_size"], proof["proof"], proof["root"]
        )

    def test_proof_endpoint_is_project_scoped(self, client, tmp_path, monkeypatch):
        """Tenant A cannot fetch inclusion proofs for tenant B's runs."""
        import asyncio
        from app.core.crypto import hash_api_key
        from app.db import database
        from app.db.models import ApiKey, Organization, Project

        log_path = tmp_path / "t.log"
        monkeypatch.setattr(settings, "transparency_log_path", str(log_path))
        raw_other = "wfl_t_" + "c" * 32

        async def _mk():
            async with database.async_session_factory() as s:
                org = Organization(name="T-Org")
                s.add(org)
                await s.flush()
                proj = Project(org_id=org.id, name="T-Proj")
                s.add(proj)
                await s.flush()
                s.add(ApiKey(project_id=proj.id, key_hash=hash_api_key(raw_other),
                             label="t", scopes=["run_tests", "admin"]))
                await s.commit()

        asyncio.run(_mk())

        with patch("workflo_executor.SandboxExecutor") as mock_cls:
            result = MagicMock()
            result.to_json.return_value = _real_signed_receipt_json()
            mock_cls.return_value.run.return_value = result
            resp = client.post(
                "/v1/runs",
                json={"repo_url": "https://github.com/example/r.git", "probe_groups": ["test"]},
                headers={"X-API-Key": raw_other},
            )
            run_id = resp.json()["run_id"]
            _wait_terminal(client, run_id, {"X-API-Key": raw_other})

        blocked = client.get(f"/v1/runs/{run_id}/proof", headers=_demo_headers(client))
        assert blocked.status_code == 404

    def test_proof_404_when_log_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "transparency_log_path", "")
        headers = _demo_headers(client)
        resp = client.get("/v1/runs/any/proof", headers=headers)
        # No such run -> 404 by scoping check before log config matters
        assert resp.status_code == 404
