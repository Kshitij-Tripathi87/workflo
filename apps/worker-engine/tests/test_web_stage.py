"""Unit tests for the web stage orchestration (config resolution + run).

Covers:
  - env vars win over workflo.yaml
  - workflo.yaml is the fallback when env is absent
  - neither -> WebConfigError with an actionable message (fail fast)
  - run_web_stage ALWAYS returns a payload (config/app/probe failures are
    reportable outcomes, not exceptions)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from workflo_worker.web.stage import (
    WebConfigError,
    resolve_web_config,
    run_web_stage,
)


@pytest.fixture
def repo_with_yaml(tmp_path: Path) -> Path:
    """A repo root with a workflo.yaml defining the web section."""
    (tmp_path / "workflo.yaml").write_text(
        "web:\n"
        "  start_command: \"python app.py\"\n"
        "  port: 5000\n",
        encoding="utf-8",
    )
    return tmp_path


class TestResolveWebConfig:
    def test_env_wins_over_workflo_yaml(self, repo_with_yaml):
        """Explicit env config overrides workflo.yaml — the env is set by
        the CLI/API from explicit user intent."""
        cfg = resolve_web_config(
            str(repo_with_yaml),
            env={"WORKFLO_START_COMMAND": "python custom.py", "WORKFLO_WEB_PORT": "9000"},
        )
        assert cfg == {"start_command": "python custom.py", "port": 9000}

    def test_workflo_yaml_is_the_fallback(self, repo_with_yaml):
        """No env -> the repo's workflo.yaml web section is used."""
        cfg = resolve_web_config(str(repo_with_yaml), env={})
        assert cfg == {"start_command": "python app.py", "port": 5000}

    def test_env_port_only_and_yaml_start_command(self, repo_with_yaml):
        """Mixed resolution: each value falls back independently."""
        cfg = resolve_web_config(
            str(repo_with_yaml),
            env={"WORKFLO_WEB_PORT": "8080"},
        )
        assert cfg["port"] == 8080
        assert cfg["start_command"] == "python app.py"

    def test_neither_source_raises_with_actionable_message(self, tmp_path):
        """No env AND no workflo.yaml -> WebConfigError naming what's
        missing and how to fix it. Fail fast, before any container work."""
        with pytest.raises(WebConfigError, match="start_command, port"):
            resolve_web_config(str(tmp_path), env={})

    def test_non_integer_port_raises(self, repo_with_yaml):
        with pytest.raises(WebConfigError, match="not an integer"):
            resolve_web_config(
                str(repo_with_yaml),
                env={"WORKFLO_START_COMMAND": "python app.py", "WORKFLO_WEB_PORT": "abc"},
            )

    def test_port_out_of_range_raises(self, repo_with_yaml):
        with pytest.raises(WebConfigError, match="out of range"):
            resolve_web_config(
                str(repo_with_yaml),
                env={"WORKFLO_START_COMMAND": "python app.py", "WORKFLO_WEB_PORT": "0"},
            )

    def test_malformed_workflo_yaml_falls_through_to_error(self, tmp_path):
        """A broken workflo.yaml must not crash resolution — it just
        contributes nothing, and the missing-config error fires."""
        (tmp_path / "workflo.yaml").write_text("web: [not-a-map", encoding="utf-8")
        with pytest.raises(WebConfigError):
            resolve_web_config(str(tmp_path), env={})


class TestRunWebStage:
    def test_always_returns_payload_on_success(self, tmp_path):
        """Happy path: base_url + probes + app_start_error=None."""
        (tmp_path / "workflo.yaml").write_text(
            "web:\n  start_command: \"python app.py\"\n  port: 5000\n",
            encoding="utf-8",
        )
        fake_proc = object()

        with patch(
            "workflo_worker.web.stage.start_app_under_test",
            return_value=fake_proc,
        ), patch(
            "workflo_worker.web.stage.run_web_probes",
            return_value=[{"name": "page_loads", "passed": True, "detail": "status=200"}],
        ), patch(
            "workflo_worker.web.stage.stop_app_under_test",
        ) as mock_stop:
            payload = run_web_stage(str(tmp_path), env={})

        assert payload["base_url"] == "http://127.0.0.1:5000"
        assert payload["app_start_error"] is None
        assert payload["probes"][0]["passed"] is True
        mock_stop.assert_called_once_with(fake_proc)

    def test_app_start_failure_is_a_payload_not_an_exception(self, tmp_path):
        """App crashes -> run_web_stage returns a payload with
        app_start_error set (reportable outcome), it does NOT raise."""
        (tmp_path / "workflo.yaml").write_text(
            "web:\n  start_command: \"python broken.py\"\n  port: 5000\n",
            encoding="utf-8",
        )

        with patch(
            "workflo_worker.web.stage.start_app_under_test",
            side_effect=RuntimeError("app process exited early with code 1"),
        ):
            payload = run_web_stage(str(tmp_path), env={})

        assert payload["app_start_error"] is not None
        assert "app process exited early" in payload["app_start_error"]
        assert payload["probes"] == []

    def test_missing_config_is_a_payload_not_an_exception(self, tmp_path):
        """No config at all -> payload with app_start_error (the worker
        reports it via WORKFLO_WEB_PROBES; the executor records it in the
        receipt as a failed web tier, not a crashed worker)."""
        payload = run_web_stage(str(tmp_path), env={})
        assert payload["app_start_error"] is not None
        assert "start_command" in payload["app_start_error"]
