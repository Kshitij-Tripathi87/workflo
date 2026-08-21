"""Tests for run submission, status, and completion — frozen contract.

Backs docs/api_contract.md v1:
  - POST /v1/runs accepts a RunRequest, returns RunStatus(status=queued)
  - GET /v1/runs/{run_id} polls RunStatus; completed carries a receipt,
    failed carries an error (never both, never neither for terminal states)
  - POST /v1/auth/demo-token issues the fixed demo key
  - Auth via X-API-Key header (legacy X-TenantShield-Key still accepted)
"""

from unittest.mock import patch, MagicMock


def _demo_headers(client):
    """Bootstrap a valid API key via the frozen demo-token endpoint."""
    resp = client.post("/v1/auth/demo-token")
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["api_key"]}


def test_demo_token_returns_fixed_key(client):
    """The demo key is deterministic — same key on repeated calls."""
    r1 = client.post("/v1/auth/demo-token")
    r2 = client.post("/v1/auth/demo-token")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["api_key"] == r2.json()["api_key"]
    assert r1.json()["api_key"].startswith("wfl_")


def test_submit_run_without_auth_fails(client):
    resp = client.post("/v1/runs", json={"repo_url": "https://x.com/r.git", "probe_groups": ["test"]})
    assert resp.status_code == 401


def test_legacy_header_still_accepted(client):
    """X-TenantShield-Key (legacy) is accepted for backwards compat."""
    resp = client.post("/v1/auth/demo-token")
    raw_key = resp.json()["api_key"]
    headers = {"X-TenantShield-Key": raw_key}
    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://x.com/r.git", "probe_groups": ["test"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


def test_submit_run_returns_queued_status(client):
    """Frozen contract: POST returns RunStatus(status=queued) with a
    server-assigned run_id, receipt and error both null."""
    headers = _demo_headers(client)
    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "queued"
    assert data["run_id"]
    assert data["receipt"] is None
    assert data["error"] is None
    assert "created_at" in data


def test_submit_run_with_web_missing_config_is_400(client):
    """web in probe_groups without start_command/port -> 400 with the
    actionable validation message (fail-fast pre-container)."""
    headers = _demo_headers(client)
    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["web"]},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "start_command" in resp.json()["detail"]
    assert "port" in resp.json()["detail"]


def test_submit_run_unknown_probe_group_rejected(client):
    """Unknown probe groups are rejected by the RunRequest contract
    validator (422 from Pydantic's Literal, pre-container)."""
    headers = _demo_headers(client)
    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["fuzz"]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_get_nonexistent_run_404(client):
    resp = client.get("/v1/runs/nonexistent-id")
    assert resp.status_code == 404


class TestRunExecutionOutcomes:
    """Background execution semantics: completed-with-receipt vs failed-with-error.

    These tests patch the SandboxExecutor so no Docker is invoked. The
    run executes in a background asyncio task; the test polls GET until
    the terminal state appears (bounded retry loop).
    """

    def _wait_terminal(self, client, run_id, headers, attempts=50):
        import time
        for _ in range(attempts):
            resp = client.get(f"/v1/runs/{run_id}", headers=headers)
            assert resp.status_code == 200, resp.text
            status = resp.json()["status"]
            if status in ("completed", "failed"):
                return resp.json()
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} never reached terminal state")

    def _fake_result(self):
        """A minimal SandboxRunResult stand-in with to_json()."""
        result = MagicMock()
        result.to_json.return_value = '{"receipt": true, "sandbox_id": "sb-1"}'
        return result

    def test_run_completes_with_receipt(self, client):
        headers = _demo_headers(client)
        # The patch must cover the POLLING too: the run executes in a
        # background asyncio task that only runs while later requests
        # drive the event loop — if the patch exits first, the real
        # SandboxExecutor would be invoked.
        with patch("workflo_executor.SandboxExecutor") as mock_cls:
            mock_cls.return_value.run.return_value = self._fake_result()
            resp = client.post(
                "/v1/runs",
                json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["run_id"]
            data = self._wait_terminal(client, run_id, headers)

        assert data["status"] == "completed"
        # Receipt present (tests may fail INSIDE the receipt — status is
        # about infrastructure, not test outcomes).
        assert data["receipt"] is not None
        assert data["error"] is None

    def test_run_infrastructure_failure_has_error_no_receipt(self, client):
        """An executor crash is status=failed with error and NO receipt —
        the contract distinguishes infra crashes from test failures."""
        headers = _demo_headers(client)
        with patch("workflo_executor.SandboxExecutor") as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("Ollama did not respond within 30s")
            resp = client.post(
                "/v1/runs",
                json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["run_id"]
            data = self._wait_terminal(client, run_id, headers)

        assert data["status"] == "failed"
        assert data["receipt"] is None
        assert "Ollama" in data["error"]


def test_legacy_lifecycle_endpoints_still_work(client):
    """Legacy worker-callback endpoints (logs/complete) are preserved for
    the queue-mode worker streamer — they are NOT part of frozen v1."""
    headers = _demo_headers(client)

    # Legacy submission shape is NOT accepted anymore (frozen contract) —
    # use the contract shape.
    resp = client.post(
        "/v1/runs",
        json={"repo_url": "https://github.com/example/repo.git", "probe_groups": ["test"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    # Stream logs (simulating worker)
    resp = client.post(f"/v1/runs/{run_id}/logs", params={"log_line": "Starting tests..."}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ack"] is True

    # Complete the run (simulating worker)
    resp = client.post(
        f"/v1/runs/{run_id}/complete",
        json={"total": 5, "passed": 5, "failed": 0, "skipped": 0, "duration_seconds": 12.5},
        headers=headers,
    )
    assert resp.status_code == 200

    # Legacy status view
    resp = client.get(f"/v1/runs/{run_id}/legacy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["summary"]["total"] == 5
