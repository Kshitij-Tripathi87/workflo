"""Tests for the agent runner loop (task spec -> governed tools -> report)."""

import json
from pathlib import Path

import pytest

from workflo_worker.agent_runner import (
    load_task,
    execute_step,
    main,
    TASK_PATH,
    REPORT_PATH,
    RECORDS_PATH,
    APP_LOG_PATH,
)


def _task(tmp_path: Path, steps: list) -> Path:
    task = {"task_id": "t-1", "steps": steps}
    p = tmp_path / "agent_task.json"
    p.write_text(json.dumps(task))
    return p


class TestLoadTask:
    def test_valid_task(self, tmp_path):
        p = _task(tmp_path, [{"tool": "read_log"}])
        task = load_task(p)
        assert task["steps"] == [{"tool": "read_log"}]

    def test_missing_task_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_task(tmp_path / "nope.json")

    def test_invalid_task_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"no_steps": True}))
        with pytest.raises(ValueError):
            load_task(p)


class TestExecuteStep:
    def test_observation_only_step_ok(self, tmp_path):
        from workflo_worker.agent_tools import ToolGateway
        gw = ToolGateway(tmp_path / "records.jsonl",
                         app_log_path=tmp_path / "app.log")
        obs = execute_step(gw, {"tool": "read_log", "args": {}})
        assert obs["ok"] is True  # log missing = observation, not failure
        assert obs["denied"] is False

    def test_expectation_met(self, tmp_path):
        from workflo_worker.agent_tools import ToolGateway
        gw = ToolGateway(tmp_path / "records.jsonl",
                         app_log_path=tmp_path / "app.log")

        # http step denied (external host) -> observation ok=False
        obs = execute_step(gw, {
            "tool": "http_get",
            "args": {"url": "http://exfiltrate.example.com/"},
        })
        assert obs["ok"] is False
        assert obs["denied"] is True

    def test_denied_step_is_observation(self, tmp_path):
        from workflo_worker.agent_tools import ToolGateway
        gw = ToolGateway(tmp_path / "records.jsonl")
        obs = execute_step(gw, {
            "tool": "http_get",
            "args": {"url": "http://exfiltrate.example.com/steal"},
        })
        assert obs["ok"] is False
        assert obs["denied"] is True
        assert "not under" in obs["detail"]


class TestMain:
    def test_full_run_writes_report(self, tmp_path, monkeypatch):
        """The full runner loop: task -> governed tools -> report."""
        log = tmp_path / "app.log"
        log.write_text("app started\n")

        task = {
            "task_id": "t-full",
            "steps": [
                {"tool": "read_log", "args": {"lines": 5}},
                {"tool": "list_files", "args": {"path": str(tmp_path)}},
                {"tool": "http_get", "args": {"url": "http://evil.example.com/"}},
            ],
        }
        task_path = tmp_path / "agent_task.json"
        task_path.write_text(json.dumps(task))

        # Point the runner's module-level paths at the temp dir
        monkeypatch.setattr("workflo_worker.agent_runner.TASK_PATH", task_path)
        monkeypatch.setattr(
            "workflo_worker.agent_runner.REPORT_PATH", tmp_path / "agent_report.json"
        )
        monkeypatch.setattr(
            "workflo_worker.agent_runner.RECORDS_PATH", tmp_path / "records.jsonl"
        )
        # list_files allowlist: point at tmp_path
        import workflo_worker.agent_tools as at
        monkeypatch.setattr(at, "ALLOWED_FILE_ROOTS", (str(tmp_path),))

        assert main() == 0

        report = json.loads((tmp_path / "agent_report.json").read_text())
        assert report["steps_total"] == 3
        assert report["steps_completed"] == 2   # read_log + list_files
        assert report["steps_failed"] == 1      # denied external http
        assert report["denied_attempts"] == 1
        assert report["tool_calls"] == 3
        assert "read_log" in report["tools_used"]

        # The denied attempt is visible as a failing observation
        denied_obs = [o for o in report["observations"] if o.get("denied")]
        assert len(denied_obs) == 1
        assert "not under" in denied_obs[0]["detail"]

    def test_missing_task_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "workflo_worker.agent_runner.TASK_PATH", tmp_path / "nope.json"
        )
        with pytest.raises(FileNotFoundError):
            main()
