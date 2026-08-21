"""Unit tests for the security stage orchestration (config resolution + run).

Covers:
  - security-specific env vars win over workflo.yaml
  - web-tier env vars are a fallback when security env is absent
  - workflo.yaml security: section is used (with web: as fallback)
  - neither -> SecurityConfigError with an actionable message (fail fast)
  - run_security_stage ALWAYS returns a payload (config/app/probe failures
    are reportable outcomes, not exceptions)
  - WORKFLO_API_BASE_URL is set during the run and restored afterwards
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from workflo_worker.security.stage import (
    SecurityConfigError,
    resolve_security_config,
    run_security_stage,
)


@pytest.fixture
def repo_with_security_yaml(tmp_path: Path) -> Path:
    """A repo root with a workflo.yaml defining the security section."""
    (tmp_path / "workflo.yaml").write_text(
        "security:\n"
        "  start_command: \"python app.py\"\n"
        "  port: 5000\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def repo_with_web_yaml(tmp_path: Path) -> Path:
    """A repo root with a workflo.yaml defining only the web section."""
    (tmp_path / "workflo.yaml").write_text(
        "web:\n"
        "  start_command: \"python webapp.py\"\n"
        "  port: 7000\n",
        encoding="utf-8",
    )
    return tmp_path


class TestResolveSecurityConfig:
    def test_security_env_wins_over_workflo_yaml(self, repo_with_security_yaml):
        """Explicit security env config overrides workflo.yaml."""
        cfg = resolve_security_config(
            str(repo_with_security_yaml),
            env={
                "WORKFLO_SECURITY_START_COMMAND": "python custom.py",
                "WORKFLO_SECURITY_PORT": "9000",
            },
        )
        assert cfg == {"start_command": "python custom.py", "port": 9000}

    def test_security_workflo_yaml_is_the_fallback(self, repo_with_security_yaml):
        """No env -> the repo's workflo.yaml security section is used."""
        cfg = resolve_security_config(str(repo_with_security_yaml), env={})
        assert cfg == {"start_command": "python app.py", "port": 5000}

    def test_web_env_vars_are_a_fallback(self, repo_with_security_yaml):
        """When security env is absent, the web-tier env vars are used."""
        cfg = resolve_security_config(
            str(repo_with_security_yaml),
            env={
                "WORKFLO_START_COMMAND": "python webonly.py",
                "WORKFLO_WEB_PORT": "8080",
            },
        )
        assert cfg == {"start_command": "python webonly.py", "port": 8080}

    def test_web_workflo_yaml_is_a_fallback(self, repo_with_web_yaml):
        """No security env and only a web: section in workflo.yaml -> use web."""
        cfg = resolve_security_config(str(repo_with_web_yaml), env={})
        assert cfg == {"start_command": "python webapp.py", "port": 7000}

    def test_security_env_overrides_web_env(self, repo_with_security_yaml):
        """Security env takes precedence over web env."""
        cfg = resolve_security_config(
            str(repo_with_security_yaml),
            env={
                "WORKFLO_SECURITY_START_COMMAND": "python sec.py",
                "WORKFLO_SECURITY_PORT": "6000",
                "WORKFLO_START_COMMAND": "python web.py",
                "WORKFLO_WEB_PORT": "7000",
            },
        )
        assert cfg == {"start_command": "python sec.py", "port": 6000}

    def test_mixed_resolution_each_value_independent(self, repo_with_security_yaml):
        """Each value falls back independently."""
        cfg = resolve_security_config(
            str(repo_with_security_yaml),
            env={"WORKFLO_SECURITY_PORT": "8080"},
        )
        assert cfg["port"] == 8080
        assert cfg["start_command"] == "python app.py"

    def test_neither_source_raises_with_actionable_message(self, tmp_path):
        """No env AND no workflo.yaml -> SecurityConfigError naming what's
        missing and how to fix it. Fail fast, before any container work."""
        with pytest.raises(SecurityConfigError, match="start_command, port"):
            resolve_security_config(str(tmp_path), env={})

    def test_non_integer_port_raises(self, repo_with_security_yaml):
        with pytest.raises(SecurityConfigError, match="not an integer"):
            resolve_security_config(
                str(repo_with_security_yaml),
                env={
                    "WORKFLO_SECURITY_START_COMMAND": "python app.py",
                    "WORKFLO_SECURITY_PORT": "abc",
                },
            )

    def test_port_out_of_range_raises(self, repo_with_security_yaml):
        with pytest.raises(SecurityConfigError, match="out of range"):
            resolve_security_config(
                str(repo_with_security_yaml),
                env={
                    "WORKFLO_SECURITY_START_COMMAND": "python app.py",
                    "WORKFLO_SECURITY_PORT": "0",
                },
            )

    def test_malformed_workflo_yaml_falls_through_to_error(self, tmp_path):
        """A broken workflo.yaml must not crash resolution — it just
        contributes nothing, and the missing-config error fires."""
        (tmp_path / "workflo.yaml").write_text("security: [not-a-map", encoding="utf-8")
        with pytest.raises(SecurityConfigError):
            resolve_security_config(str(tmp_path), env={})


class TestRunSecurityStage:
    def test_always_returns_payload_on_success(self, tmp_path):
        """Happy path: base_url + probes + app_start_error=None.

        The security tier uses the same app bootstrap primitive as the web
        tier. We mock start_app_under_test/stop_app_under_test and the
        probe runner path.
        """
        (tmp_path / "workflo.yaml").write_text(
            "security:\n  start_command: \"python app.py\"\n  port: 5000\n",
            encoding="utf-8",
        )
        fake_proc = object()

        with patch(
            "workflo_worker.security.stage.start_app_under_test",
            return_value=fake_proc,
        ), patch(
            "workflo_worker.security.stage.stop_app_under_test",
        ) as mock_stop, patch(
            "workflo_worker.security.stage._run_security_probes",
            return_value=[{"name": "cross_tenant_read_denied", "passed": True, "detail": "status=403"}],
        ):
            payload = run_security_stage(str(tmp_path), env={})

        assert payload["base_url"] == "http://127.0.0.1:5000"
        assert payload["app_start_error"] is None
        assert payload["probes"][0]["passed"] is True
        mock_stop.assert_called_once_with(fake_proc)

    def test_app_start_failure_is_a_payload_not_an_exception(self, tmp_path):
        """App crashes -> run_security_stage returns a payload with
        app_start_error set (reportable outcome), it does NOT raise."""
        (tmp_path / "workflo.yaml").write_text(
            "security:\n  start_command: \"python broken.py\"\n  port: 5000\n",
            encoding="utf-8",
        )

        with patch(
            "workflo_worker.security.stage.start_app_under_test",
            side_effect=RuntimeError("app process exited early with code 1"),
        ):
            payload = run_security_stage(str(tmp_path), env={})

        assert payload["app_start_error"] is not None
        assert "app process exited early" in payload["app_start_error"]
        assert payload["probes"] == []

    def test_missing_config_is_a_payload_not_an_exception(self, tmp_path):
        """No config at all -> payload with app_start_error (the worker
        reports it via WORKFLO_SECURITY_PROBES; the executor records it in
        the receipt as a failed security tier, not a crashed worker)."""
        payload = run_security_stage(str(tmp_path), env={})
        assert payload["app_start_error"] is not None
        assert "start_command" in payload["app_start_error"]

    def test_sets_and_restores_workflo_api_base_url(self, tmp_path):
        """run_security_stage must set WORKFLO_API_BASE_URL for the probes
        and restore the original value (or remove it) afterwards."""
        (tmp_path / "workflo.yaml").write_text(
            "security:\n  start_command: \"python app.py\"\n  port: 5050\n",
            encoding="utf-8",
        )
        # Pre-existing value must be restored.
        os.environ["WORKFLO_API_BASE_URL"] = "http://pre-existing.test"
        fake_proc = object()

        try:
            with patch(
                "workflo_worker.security.stage.start_app_under_test",
                return_value=fake_proc,
            ), patch(
                "workflo_worker.security.stage.stop_app_under_test",
            ), patch(
                "workflo_worker.security.stage._run_security_probes",
            ) as mock_probes:
                # Capture the value of WORKFLO_API_BASE_URL at probe time.
                def _capture(*args, **kwargs):
                    mock_probes.captured_url = os.environ.get("WORKFLO_API_BASE_URL")
                    return []
                mock_probes.side_effect = _capture

                payload = run_security_stage(str(tmp_path), env={})

            # At probe time the env was set to the app base URL.
            assert mock_probes.captured_url == "http://127.0.0.1:5050"
            assert payload["app_start_error"] is None
        finally:
            # The original value must be restored, not left as the app URL.
            assert os.environ["WORKFLO_API_BASE_URL"] == "http://pre-existing.test"
            del os.environ["WORKFLO_API_BASE_URL"]

    def test_removes_workflo_api_base_url_when_absent_before(self, tmp_path):
        """If WORKFLO_API_BASE_URL was unset before the run, it must be
        removed after (not left as the app URL, which would leak into
        subsequent stages like the web tier)."""
        (tmp_path / "workflo.yaml").write_text(
            "security:\n  start_command: \"python app.py\"\n  port: 5051\n",
            encoding="utf-8",
        )
        os.environ.pop("WORKFLO_API_BASE_URL", None)
        fake_proc = object()

        with patch(
            "workflo_worker.security.stage.start_app_under_test",
            return_value=fake_proc,
        ), patch(
            "workflo_worker.security.stage.stop_app_under_test",
        ), patch(
            "workflo_worker.security.stage._run_security_probes",
            return_value=[],
        ):
            run_security_stage(str(tmp_path), env={})

        assert "WORKFLO_API_BASE_URL" not in os.environ
