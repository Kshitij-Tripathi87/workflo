"""Tests for the web-tier integration points in the sandbox executor:

  1. _parse_web_probes — parsing the WORKFLO_WEB_PROBES line into a
     WebProbeResult (None when absent / unparseable).
  2. Env-var validation in docker_runner — WORKFLO_START_COMMAND /
     WORKFLO_WEB_PORT (underscore keys) must pass _SAFE_NAME_RE so the
     web tier's env config can reach the container.
"""

from __future__ import annotations

import pytest

from workflo_executor.docker_runner import (
    ContainerConfig,
    _validate_safe_name,
    create_container,
)
from workflo_executor.executor import SandboxExecutor
from workflo_schema.sandbox import WebProbeResult


def _container_result_with(stdout: str):
    from workflo_executor.docker_runner import ContainerResult
    return ContainerResult(
        container_id="c1", returncode=0, stdout=stdout, stderr="", timed_out=False,
    )


class TestParseWebProbes:
    def test_parses_healthy_payload(self):
        ex = SandboxExecutor()
        out = (
            'WORKFLO_REPORT: {"total":1,"passed":1}\n'
            'WORKFLO_WEB_PROBES: {"base_url":"http://127.0.0.1:5000",'
            '"probes":[{"name":"page_loads","passed":true,"detail":"status=200"}],'
            '"app_start_error":null}\n'
        )
        result = ex._parse_web_probes(_container_result_with(out))
        assert isinstance(result, WebProbeResult)
        assert result.base_url == "http://127.0.0.1:5000"
        assert result.probes[0]["name"] == "page_loads"
        assert result.probes[0]["passed"] is True
        assert result.app_start_error is None

    def test_parses_app_start_error_payload(self):
        """A web run where the app-under-test crashed must still parse —
        app_start_error is a valid, reportable outcome."""
        ex = SandboxExecutor()
        out = (
            'WORKFLO_WEB_PROBES: {"base_url":"http://127.0.0.1:5000",'
            '"probes":[],"app_start_error":"RuntimeError: app process exited early with code 1"}\n'
        )
        result = ex._parse_web_probes(_container_result_with(out))
        assert result.probes == []
        assert "exited early" in result.app_start_error

    def test_absent_line_returns_none(self):
        """No WORKFLO_WEB_PROBES line = web tier not requested = None.
        This is how the receipt distinguishes 'not requested' from 'ran
        and failed' (which would be a parsed payload with failures)."""
        ex = SandboxExecutor()
        out = 'WORKFLO_REPORT: {"total":1,"passed":1}\n'
        assert ex._parse_web_probes(_container_result_with(out)) is None

    def test_malformed_line_is_ignored_not_fatal(self):
        """A corrupt WORKFLO_WEB_PROBES line must not crash the run —
        treated as absent (same discipline as the model-teardown parser)."""
        ex = SandboxExecutor()
        out = 'WORKFLO_WEB_PROBES: {{{not-json\nWORKFLO_REPORT: {"total":1}\n'
        assert ex._parse_web_probes(_container_result_with(out)) is None


class TestWebEnvKeysPassSafeNameValidation:
    def test_underscore_env_keys_are_valid(self):
        """WORKFLO_START_COMMAND / WORKFLO_WEB_PORT use underscores, which
        env var keys conventionally do — these MUST pass validation."""
        _validate_safe_name("WORKFLO_START_COMMAND", "env key")
        _validate_safe_name("WORKFLO_WEB_PORT", "env key")

    def test_create_container_passes_env_keys_through(self):
        """End-to-end: a ContainerConfig carrying web env vars builds a
        docker create command that passes -e WORKFLO_*=... — proving the
        CLI -> executor -> container env path is unbroken."""
        import subprocess
        from unittest.mock import patch

        config = ContainerConfig(
            image="workflo-worker-web:latest",
            command=["python", "-m", "workflo_worker.main"],
            env={
                "PROBE_GROUPS": '["web"]',
                "WORKFLO_START_COMMAND": "python app.py",
                "WORKFLO_WEB_PORT": "5000",
            },
        )
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc123\n", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            container_id = create_container(config)

        assert container_id == "abc123"
        cmd = captured["cmd"]
        assert "-e" in cmd
        assert "WORKFLO_START_COMMAND=python app.py" in cmd
        assert "WORKFLO_WEB_PORT=5000" in cmd
