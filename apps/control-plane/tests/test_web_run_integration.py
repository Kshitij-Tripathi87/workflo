"""Track B.4 — Integration test for the API + web probes pipeline.

This is the cross-layer gluing test for the `web` tier: the frozen REST
contract (POST /v1/runs with probe_groups=["web"]) must feed a
SandboxSpec whose run_spec.env carries WORKFLO_START_COMMAND /
WORKFLO_WEB_PORT all the way to the (mocked) executor, and a signed
receipt carrying `web_probes` must come back through GET /v1/runs/{id}.

What is REAL here (no mocks):
  - RunRequest parsing (Pydantic contract validation)
  - RunRequest.to_sandbox_spec() — web env injection + goal mapping
  - The background-task execution path (_execute_run -> SandboxExecutor)
  - complete_run -> GET status round-trip through RunStatus
  - The web-missing-config fail-fast (400) against the live endpoint

The Mock ONLY substitutes the SandboxExecutor (real executor requires
Docker + Playwright), the same seam the existing frozen-contract tests
use. The worker-side web stage itself (resolve_web_config, app_starter,
probes) is unit-tested in apps/worker-engine/tests/test_web_stage.py.
"""

from unittest.mock import patch, MagicMock

# A realistic signed-receipt JSON string (what SandboxRunResult.to_json()
# returns) with the web tier populated.
_WEB_RECEIPT_JSON = (
    '{'
    '  "sandbox_id": "sb-web-1",'
    '  "issued_at": "2026-08-21T16:42:11.123456+00:00",'
    '  "run_report": {"sandbox_id": "sb-web-1", "total": 2, "passed": 2, '
    '    "failed": 0, "skipped": 0, "duration_seconds": 1.2, '
    '    "soc2_controls_covered": [], "findings": []},'
    '  "teardown_proof": {"sandbox_id": "sb-web-1", "container_removed": true, '
    '    "filesystem_removed": true, "destroyed_at": "2026-08-21T16:42:12.0+00:00"},'
    '  "canary_check": {"sandbox_id": "sb-web-1", "attempted_at": "2026-08-21T16:42:10.0+00:00", '
    '    "target_host": "https://example.com", "request_succeeded": false, "error": "blocked"},'
    '  "lifecycle_events": [],'
    '  "web_probes": {'
    '    "base_url": "http://127.0.0.1:5000",'
    '    "probes": ['
    '      {"name": "page_loads", "passed": true, "detail": "status=200"},'
    '      {"name": "no_console_errors", "passed": true, "detail": "0 console errors"}'
    '    ],'
    '    "app_start_error": null'
    '  },'
    '  "signature_algorithm": "ed25519",'
    '  "public_key_fingerprint": "abc123",'
    '  "signature": "SIG"'
    '}'
)


def _demo_headers(client):
    resp = client.post("/v1/auth/demo-token")
    assert resp.status_code == 200, resp.text
    return {"X-API-Key": resp.json()["api_key"]}


def _wait_terminal(client, run_id, headers, attempts=50):
    import time

    for _ in range(attempts):
        resp = client.get(f"/v1/runs/{run_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        status = resp.json()["status"]
        if status in ("completed", "failed"):
            return resp.json()
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached terminal state")


def _fake_executor_with_spec_capture():
    """Patch SandboxExecutor, capturing the SandboxSpec each run() receives.

    Returns (mock_cls, spec_list) — spec_list fills with the spec dicts.
    """
    mock_cls = MagicMock()
    spec_list = []

    def fake_run(spec):
        spec_list.append(spec.model_dump(mode="json"))
        result = MagicMock()
        result.to_json.return_value = _WEB_RECEIPT_JSON
        return result

    mock_cls.return_value.run.side_effect = fake_run
    return mock_cls, spec_list


class TestWebRunThroughApi:
    def test_web_run_accepted_and_completed_with_web_probes(self, client):
        """The full API loop for a web run: 200 queued -> executor receives
        the web spec -> GET returns completed with web_probes in the
        receipt."""
        headers = _demo_headers(client)
        mock_cls, specs = _fake_executor_with_spec_capture()

        with patch("workflo_executor.SandboxExecutor", mock_cls):
            resp = client.post(
                "/v1/runs",
                json={
                    "repo_url": "https://github.com/example/my-saas-app.git",
                    "probe_groups": ["web", "security"],
                    "start_command": "python app.py",
                    "port": 5000,
                    "config": {"timeout_seconds": 300},
                },
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["run_id"]
            data = _wait_terminal(client, run_id, headers)

        assert data["status"] == "completed"
        receipt = data["receipt"]
        assert receipt is not None
        # The web tier path made it all the way into the returned receipt.
        web_probes = receipt["web_probes"]
        assert web_probes["base_url"] == "http://127.0.0.1:5000"
        names = [p["name"] for p in web_probes["probes"]]
        assert "page_loads" in names and "no_console_errors" in names
        assert web_probes["app_start_error"] is None

        # The executor really was called exactly once, with the web spec.
        assert len(specs) == 1
        spec = specs[0]
        assert "web" in spec["run_spec"]["probe_groups"]
        assert spec["run_spec"]["goal"] == "web"
        assert spec["run_spec"]["env"] == {
            "WORKFLO_START_COMMAND": "python app.py",
            "WORKFLO_WEB_PORT": "5000",
        }
        assert spec["repo_url"] == "https://github.com/example/my-saas-app.git"
        assert spec["timeout_seconds"] == 300

    def test_non_web_run_does_not_get_web_env(self, client):
        """Negative control: a plain test+security run must NOT carry the
        WORKFLO_* env vars — env pollution would make the worker start an
        app when it wasn't asked to."""
        headers = _demo_headers(client)
        mock_cls, specs = _fake_executor_with_spec_capture()

        with patch("workflo_executor.SandboxExecutor", mock_cls):
            resp = client.post(
                "/v1/runs",
                json={
                    "repo_url": "https://github.com/example/my-saas-app.git",
                    "probe_groups": ["test", "security"],
                },
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["run_id"]
            _wait_terminal(client, run_id, headers)

        assert len(specs) == 1
        spec = specs[0]
        assert spec["run_spec"]["env"] == {}
        assert "WORKFLO_START_COMMAND" not in spec["run_spec"]["env"]
        assert "WORKFLO_WEB_PORT" not in spec["run_spec"]["env"]
        # Internal vocabulary, not the public one.
        assert spec["run_spec"]["probe_groups"] == ["surface", "security"]

    def test_web_missing_config_fails_fast_with_actionable_400(self, client):
        """The fail-fast validation is enforced at the API: web without
        start_command/port -> 400 naming both — before any executor work."""
        headers = _demo_headers(client)
        resp = client.post(
            "/v1/runs",
            json={
                "repo_url": "https://github.com/example/my-saas-app.git",
                "probe_groups": ["web"],
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert "start_command" in detail
        assert "port" in detail
        assert "web" in detail

    def test_web_receipt_round_trips_through_runstatus(self, client):
        """The receipt with web_probes survives the RunStatus JSON
        boundary exactly — dict in, dict out."""
        headers = _demo_headers(client)
        mock_cls, _ = _fake_executor_with_spec_capture()

        with patch("workflo_executor.SandboxExecutor", mock_cls):
            resp = client.post(
                "/v1/runs",
                json={
                    "repo_url": "https://github.com/example/my-saas-app.git",
                    "probe_groups": ["web"],
                    "start_command": "python app.py",
                    "port": 5000,
                },
                headers=headers,
            )
            run_id = resp.json()["run_id"]
            final = _wait_terminal(client, run_id, headers)

        # The GET body is exactly the RunStatus wire format.
        assert set(final) == {"run_id", "status", "created_at", "receipt", "error"}
        assert final["status"] == "completed"
        assert final["receipt"]["web_probes"]["probes"][0]["name"] == "page_loads"
