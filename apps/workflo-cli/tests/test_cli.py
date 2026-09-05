"""Tests for the workflo CLI."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import pytest
from click.testing import CliRunner

from workflo_cli.main import cli
from workflo_schema.sandbox import RunReport, TeardownProof, CanaryCheckResult
from cryptography.hazmat.primitives import serialization


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def clean_llm_config(monkeypatch, tmp_path):
    """Isolate the LLM config to a temp dir and clear it after."""
    monkeypatch.setenv("WORKFLO_CONFIG_DIR", str(tmp_path))
    from workflo_cli import llm_config

    yield llm_config
    llm_config.clear_llm_config()


def _fake_session_info():
    """Return a SessionInfo object representing a logged-in user."""
    from cortex_auth.profile import SessionInfo
    return SessionInfo(
        user_id="user-1",
        email="test@example.com",
        organization_id="org-1",
        organization_name="Test Org",
        workspace_id="ws-1",
        workspace_name="Test Workspace",
        product="workflo",
        scopes=["workflo:runs:create", "workflo:runs:read"],
        access_token="fake-access-token",
        access_token_expires_at=datetime.now(UTC).timestamp() + 3600,
        is_service_token=False,
    )


@pytest.fixture(autouse=True)
def mock_auth_authenticated(monkeypatch):
    """Default: every test starts in an authenticated state.

    `workflo run` now requires an authenticated user, so the test suite
    needs a logged-in default. Tests that exercise the unauthenticated path
    (TestAuthGate) override this by calling ``monkeypatch.setattr`` on
    ``cortex_auth.session.AuthSession`` themselves — monkeypatch unwinds
    in reverse order, so the test-level patch wins during the test body.
    """
    fake_session = _fake_session_info()
    fake_auth_session = MagicMock()
    fake_auth_session.status.return_value = fake_session
    monkeypatch.setattr(
        "cortex_auth.session.AuthSession",
        MagicMock(return_value=fake_auth_session),
    )
    yield fake_auth_session


class TestCLI:
    @pytest.fixture(autouse=True)
    def _clean_llm(self, clean_llm_config):
        pass

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.1.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "verify" in result.output
        assert "keygen" in result.output

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-test-001")
    def test_run_surface_only(self, mock_id, mock_executor_cls, mock_keypair, runner):
        """`workflo run --repo <url> --test` should call executor with surface probe group."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-test-001",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-test-001", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-test-001",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-test-001",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-test-001", total=5, passed=5),
            lifecycle_events=[],
            elapsed_seconds=1.5,
            success=True,
        )

        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test", "--output", "report.json"
            ])

            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
            mock_executor.run.assert_called_once()
            # Verify the spec passed to executor has probe_groups
            called_spec = mock_executor.run.call_args[0][0]
            assert called_spec.run_spec["probe_groups"] == ["surface"]
            assert "surface" in called_spec.run_spec["markers"]

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-test-002")
    def test_run_surface_and_security(self, mock_id, mock_executor_cls, mock_keypair, runner):
        """`workflo run --repo <url> --test --security` should include both probe groups."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-test-002",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-test-002", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-test-002",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-test-002",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-test-002", total=5, passed=5),
            lifecycle_events=[],
            elapsed_seconds=1.5,
            success=True,
        )

        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--test", "--security",
                "--start-command", "python app.py", "--port", "5000",
                "--output", "report.json"
            ])

            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
            called_spec = mock_executor.run.call_args[0][0]
            assert "surface" in called_spec.run_spec["probe_groups"]
            assert "security" in called_spec.run_spec["probe_groups"]
            assert set(called_spec.run_spec["probe_groups"]) == {"surface", "security"}
            # Security config should flow through env vars
            assert called_spec.run_spec["env"]["WORKFLO_SECURITY_START_COMMAND"] == "python app.py"
            assert called_spec.run_spec["env"]["WORKFLO_SECURITY_PORT"] == "5000"

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-test-003")
    def test_run_deep_test(self, mock_id, mock_executor_cls, mock_keypair, runner):
        """`workflo run --repo <url> --deep-test` should use deep probe group."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-test-003",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-test-003", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-test-003",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-test-003",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-test-003", total=5, passed=5),
            lifecycle_events=[],
            elapsed_seconds=1.5,
            success=True,
        )

        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--deep-test", "--output", "report.json"
            ])

            assert result.exit_code == 0
            called_spec = mock_executor.run.call_args[0][0]
            assert "deep" in called_spec.run_spec["probe_groups"]
            assert "surface" not in called_spec.run_spec["probe_groups"]  # mutually exclusive

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-test-004")
    def test_run_aggressive_test(self, mock_id, mock_executor_cls, mock_keypair, runner):
        """`workflo run --repo <url> --aggressive-test` should use aggressive probe group."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-test-004",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-test-004", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-test-004",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-test-004",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-test-004", total=5, passed=5),
            lifecycle_events=[],
            elapsed_seconds=1.5,
            success=True,
        )

        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git", "--aggressive-test", "--output", "report.json"
            ])

            assert result.exit_code == 0
            called_spec = mock_executor.run.call_args[0][0]
            assert "aggressive" in called_spec.run_spec["probe_groups"]

    def test_run_requires_at_least_one_probe_group(self, runner):
        """Running without any probe group should error."""
        result = runner.invoke(cli, ["run", "--repo", "https://github.com/example/repo.git"])
        assert result.exit_code != 0
        assert "probe group required" in result.output.lower()

    def test_run_mutually_exclusive_functional_tiers(self, runner):
        """Only one functional tier (--test/--deep-test/--aggressive-test) allowed."""
        result = runner.invoke(cli, [
            "run", "--repo", "https://github.com/example/repo.git",
            "--test", "--deep-test"
        ])
        assert result.exit_code != 0
        # Click will handle mutual exclusion via flag_value on same param

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-failure-001")
    def test_run_command_failure_exits_nonzero(
        self, mock_id, mock_executor_cls, mock_keypair, runner
    ):
        """When the run fails, the CLI exits with nonzero code."""
        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-failure-001",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-failure-001", total=3, passed=1, failed=2),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-failure-001",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-failure-001",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-failure-001", total=3, passed=1, failed=2),
            lifecycle_events=[],
            elapsed_seconds=2.0,
            success=False,
            error="2 tests failed",
        )

        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        result = runner.invoke(cli, ["run", "--repo", "https://github.com/example/repo.git", "--test"])

        assert result.exit_code == 1

    @patch("workflo_cli.main.generate_keypair")
    def test_keygen_command(self, mock_keypair, runner):
        """`workflo keygen` should print a PEM-encoded Ed25519 public key."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        result = runner.invoke(cli, ["keygen"])

        assert result.exit_code == 0
        assert "BEGIN PUBLIC KEY" in result.output
        assert "Fingerprint (SHA-256):" in result.output


class TestCLIDryRun:
    """Tests for --dry-run / --plan-only flag."""

    def test_dry_run_exits_zero(self, runner):
        """--dry-run validates spec and exits 0 without calling executor."""
        with patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls:
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--dry-run",
            ])

            assert result.exit_code == 0, f"Failed: {result.output}\n{result.exception}"
            # Executor must NOT be called in dry-run mode
            mock_executor_cls.assert_not_called()

    def test_dry_run_outputs_plan_json(self, runner):
        """--dry-run must output a JSON plan with mode=dry-run and spec_valid=true."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--security", "--dry-run",
                "--start-command", "python app.py", "--port", "5000",
            ])

            assert result.exit_code == 0
            # Find the JSON plan in stdout (we wrote it via click.echo)
            import json as _json
            lines = result.output.strip().splitlines()
            # The plan JSON is the last block on stdout
            plan = None
            for i, line in enumerate(lines):
                if line.strip() == "{":
                    plan = _json.loads("\n".join(lines[i:]))
                    break
            assert plan is not None, f"No JSON plan found in output: {result.output}"
            assert plan["mode"] == "dry-run"
            assert plan["spec_valid"] is True
            assert plan["repo"] == "https://github.com/example/repo.git"
            assert "surface" in plan["probe_groups"]
            assert "security" in plan["probe_groups"]
            assert plan["security_config"] == {"start_command": "python app.py", "port": 5000}

    def test_plan_only_is_alias_for_dry_run(self, runner):
        """`--plan-only` must work as an alias for `--dry-run`."""
        with patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls:
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--plan-only",
            ])

            assert result.exit_code == 0
            mock_executor_cls.assert_not_called()

    def test_dry_run_validates_bad_repo_url(self, runner):
        """--dry-run must still validate the repo URL before printing the plan."""
        result = runner.invoke(cli, [
            "run", "--repo", "javascript:alert(1)", "--test", "--dry-run",
        ])
        assert result.exit_code != 0
        assert "must start with" in result.output.lower() or "invalid" in result.output.lower()

    def test_dry_run_validates_bad_timeout(self, runner):
        """--dry-run must catch out-of-range timeout before printing plan."""
        result = runner.invoke(cli, [
            "run", "--repo", "https://github.com/example/repo.git",
            "--test", "--dry-run", "--timeout", "5",
        ])
        assert result.exit_code != 0
        assert "timeout" in result.output.lower()


class TestCLIConfig:
    """Tests for --config flag (YAML/JSON config file loading)."""

    @pytest.fixture(autouse=True)
    def _clean_llm(self, clean_llm_config):
        pass

    def test_config_yaml_provides_repo_and_test(self, runner, tmp_path):
        """--config loads a YAML file that provides repo + test flag."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "test: true\n"
            "timeout: 120\n"
            "memory: 1024\n",
            encoding="utf-8",
        )

        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])

            assert result.exit_code == 0, f"Failed: {result.output}\n{result.exception}"
            import json as _json
            lines = result.output.strip().splitlines()
            plan = None
            for i, line in enumerate(lines):
                if line.strip() == "{":
                    plan = _json.loads("\n".join(lines[i:]))
                    break
            assert plan is not None, f"No JSON plan found: {result.output}"
            assert plan["repo"] == "https://github.com/example/repo.git"
            assert "surface" in plan["probe_groups"]
            assert plan["timeout_seconds"] == 120
            assert plan["memory_mb"] == 1024

    def test_config_json_provides_repo_and_test(self, runner, tmp_path):
        """--config loads a JSON file that provides repo + test flag."""
        config_file = tmp_path / "workflo.json"
        config_file.write_text(
            '{"repo": "https://github.com/example/repo.git", "test": true}',
            encoding="utf-8",
        )

        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])

            assert result.exit_code == 0
            import json as _json
            lines = result.output.strip().splitlines()
            plan = None
            for i, line in enumerate(lines):
                if line.strip() == "{":
                    plan = _json.loads("\n".join(lines[i:]))
                    break
            assert plan is not None
            assert plan["repo"] == "https://github.com/example/repo.git"
            assert "surface" in plan["probe_groups"]

    def test_cli_flag_overrides_config_file(self, runner, tmp_path):
        """An explicit CLI flag must override the config file value."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/config/repo.git\n"
            "test: true\n"
            "timeout: 120\n",
            encoding="utf-8",
        )

        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file),
                "--repo", "https://github.com/cli-override/repo.git",
                "--timeout", "300",
                "--dry-run",
            ])

            assert result.exit_code == 0
            import json as _json
            lines = result.output.strip().splitlines()
            plan = None
            for i, line in enumerate(lines):
                if line.strip() == "{":
                    plan = _json.loads("\n".join(lines[i:]))
                    break
            assert plan is not None
            # CLI flag wins
            assert plan["repo"] == "https://github.com/cli-override/repo.git"
            assert plan["timeout_seconds"] == 300

    def test_config_unknown_key_rejected(self, runner, tmp_path):
        """Unknown keys in config file must be rejected (catch typos)."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "test: true\n"
            "bogus_key: should_fail\n",
            encoding="utf-8",
        )

        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])

            assert result.exit_code != 0
            assert "unknown config key" in result.output.lower()

    def test_config_missing_file_rejected(self, runner):
        """A nonexistent config file path must error cleanly."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", "nonexistent.yaml", "--dry-run",
            ])

            assert result.exit_code != 0
            assert "not found" in result.output.lower()

    def test_config_hyphenated_keys_normalized(self, runner, tmp_path):
        """Config keys with hyphens (e.g., `deep-test`) must work like underscores."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "deep-test: true\n",
            encoding="utf-8",
        )

        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])

            assert result.exit_code == 0
            import json as _json
            lines = result.output.strip().splitlines()
            plan = None
            for i, line in enumerate(lines):
                if line.strip() == "{":
                    plan = _json.loads("\n".join(lines[i:]))
                    break
            assert plan is not None
            assert "deep" in plan["probe_groups"]


class TestCLIForce:
    """Tests for --force flag (overwrite confirmation)."""

    def test_force_overwrites_existing_output(self, runner, tmp_path):
        """--force must overwrite an existing output file without prompting."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult,
            RunReport,
            SignedReceipt,
            TeardownProof,
        )

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )

        existing_output = tmp_path / "report.json"
        existing_output.write_text('{"old": "data"}', encoding="utf-8")

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-force-001",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-force-001", total=1, passed=1),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-force-001",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-force-001",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-force-001", total=1, passed=1),
            lifecycle_events=[],
            elapsed_seconds=0.5,
            success=True,
        )

        with patch("workflo_cli.main.generate_keypair", return_value=fake_signer), \
             patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls, \
             patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-force-001"):
            mock_executor = MagicMock()
            mock_executor.run.return_value = fake_result
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--output", str(existing_output), "--force",
            ])

            assert result.exit_code == 0, f"Failed: {result.output}\n{result.exception}"
            # File must be overwritten with new content
            content = existing_output.read_text(encoding="utf-8")
            assert "sandbox-force-001" in content
            assert "old" not in content

    def test_no_force_aborts_on_existing_output(self, runner, tmp_path):
        """Without --force, the CLI must abort when the output file exists."""
        existing_output = tmp_path / "report.json"
        existing_output.write_text('{"old": "data"}', encoding="utf-8")

        with patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls:
            # Use input="" to auto-answer No to the confirm prompt
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--output", str(existing_output),
            ], input="n\n")

            # Click's confirm() with "n" → Aborted → exit code 1
            assert result.exit_code != 0
            # Executor must NOT have been called
            mock_executor_cls.assert_not_called()


class TestCLIContainerRuntime:
    """Tests for the ContainerRuntime abstraction exported from workflo_executor."""

    def test_docker_container_runtime_is_default(self):
        """SandboxExecutor must default to DockerContainerRuntime."""
        from workflo_executor import SandboxExecutor, DockerContainerRuntime

        executor = SandboxExecutor()
        assert isinstance(executor.runtime, DockerContainerRuntime)

    def test_runtime_is_injectable(self):
        """SandboxExecutor must accept an arbitrary ContainerRuntime via DI."""
        from workflo_executor import SandboxExecutor
        from workflo_executor.runtime import ContainerRuntime

        class FakeRuntime:
            def create(self, config): return "fake-id"
            def start(self, container_id, timeout_seconds=30): pass
            def wait(self, container_id, timeout_seconds=600): pass
            def kill(self, container_id): pass
            def exists(self, container_id): return False

        fake = FakeRuntime()
        executor = SandboxExecutor(runtime=fake)
        assert executor.runtime is fake

    def test_container_runtime_protocol_satisfied(self):
        """DockerContainerRuntime must satisfy the ContainerRuntime Protocol."""
        from workflo_executor import DockerContainerRuntime
        from workflo_executor.runtime import ContainerRuntime

        runtime = DockerContainerRuntime()
        assert isinstance(runtime, ContainerRuntime)


def _parse_plan_json(output: str) -> dict:
    """Pull the dry-run plan JSON out of CLI stdout.

    The CLI prints a `click.echo("Sandbox ID: ...", err=True)` banner to stderr
    *first* then the plan JSON to stdout. click's CliRunner mixes stderr
    into result.output by default, so we scan for the first line that looks
    like the start of a JSON object (`{`) and parse from there.
    """
    import json as _json
    lines = output.strip().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "{":
            return _json.loads("\n".join(lines[i:]))
    raise AssertionError(f"No JSON plan found in CLI output:\n{output}")


class TestCLIDeepWorkerImage:
    """Tests for the --deep-worker-image flag + the auto-switch.

    The Phase 1.4 exit gate backing. These verify three observable layers:

      1. CLI accepts --deep-worker-image ( validated name, passed through to
         the executor constructor in a real run, surfaced in dry-run plan).
      2. CLI auto-selects the deep image when --deep-test / --aggressive-test
         is provided (and NOT when --test is provided) — this is the
         "auto-switch" advertised in --help.
      3. CLI rejects an invalid --deep-worker-image name early (defense in
         depth, same rule as --worker-image).
    """

    @pytest.fixture(autouse=True)
    def _clean_llm(self, clean_llm_config):
        pass

    def test_deep_worker_image_default_in_dry_run_for_test_tier(self, runner):
        """--test dry run: deep_worker_image is null and selected_worker_image
        is the plain surface image."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        # The plan now surfaces both fields. deep_worker_image is null
        # because the caller didn't set it AND the surface tier doesn't
        # need it — the executor will only fall back to the default deep
        # image if a deep tier is actually requested.
        assert plan["deep_worker_image"] is None
        assert plan["selected_worker_image"] == "workflo-worker:latest"

    def test_deep_worker_image_default_in_dry_run_for_deep_test_tier(self, runner):
        """`--deep-test --dry-run`: selected image is the deep default
        (workflo-worker-deep:latest) even though --deep-worker-image was
        NOT passed — the executor falls back to DEFAULT_DEEP_WORKER_IMAGE.
        This is the auto-switch."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--deep-test", "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        # deep_worker_image is still null (caller didn't pass the flag), but
        # selected_worker_image is the resolved DEFAULT_DEEP_WORKER_IMAGE —
        # that's what shows the auto-switch happened in the plan.
        assert plan["deep_worker_image"] is None
        assert plan["selected_worker_image"] == "workflo-worker-deep:latest"
        assert plan["worker_image"] == "workflo-worker:latest"
        # And the deep probe group made it through to the spec.
        assert "deep" in plan["probe_groups"]

    def test_explicit_deep_worker_image_used_for_deep_test(self, runner):
        """`--deep-test --deep-worker-image custom:latest`: selected image
        is the user's custom one (override flows through to the plan)."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--deep-test", "--deep-worker-image", "myregistry/deep:v1",
                "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["deep_worker_image"] == "myregistry/deep:v1"
        assert plan["selected_worker_image"] == "myregistry/deep:v1"
        # And worker_image (the surface one) stays the default — the deep
        # override doesn't accidentally replace the surface image.
        assert plan["worker_image"] == "workflo-worker:latest"

    def test_aggressive_test_also_uses_deep_image(self, runner):
        """--aggressive-test triggers the same auto-switch — aggressive
        probe groups need the model-bearing image too (it adds probes
        AND the chaos/fuzz layer is Phase 2+ same-image territory)."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--aggressive-test", "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["selected_worker_image"] == "workflo-worker-deep:latest"
        assert "aggressive" in plan["probe_groups"]

    def test_surface_run_ignores_deep_worker_image(self, runner):
        """`--test --deep-worker-image custom:latest`: the deep image is
        NOT applied for the surface tier — selected_worker_image remains
        --worker-image. This is the inverse of the auto-switch: passing a
        --deep-worker-image doesn't make a surface run use the deep image."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--deep-worker-image", "myregistry/deep:v1",
                "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        # The deep image is recorded (the caller asked for it) but NOT
        # selected — the surface run used the surface image.
        assert plan["deep_worker_image"] == "myregistry/deep:v1"
        assert plan["selected_worker_image"] == "workflo-worker:latest"

    def test_invalid_deep_worker_image_rejected_early(self, runner):
        """Invalid characters in --deep-worker-image: bail out in the CLI,
        just like for --worker-image. Both go through the same regex."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--deep-test", "--deep-worker-image", "evil; rm -rf /",
                "--dry-run",
            ])
        assert result.exit_code != 0
        assert "invalid deep-worker-image" in result.output.lower()

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-deep-001")
    def test_real_deep_test_run_passes_deep_image_to_executor(
        self, mock_id, mock_executor_cls, mock_keypair, runner,
    ):
        """A non-dry-run --deep-test --deep-worker-image custom:latest call
        must construct SandboxExecutor with deep_worker_image=custom:latest
        (in addition to the regular worker_image). This is the end-to-end
        wiring that makes the dry-run plan and a real run agree."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult, RunReport, SignedReceipt, TeardownProof,
        )
        from datetime import datetime

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-deep-001",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-deep-001", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-deep-001",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-deep-001",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-deep-001", total=5, passed=5),
            lifecycle_events=[],
            elapsed_seconds=1.5,
            success=True,
        )
        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--deep-test", "--deep-worker-image", "myregistry/deep:v1",
                "--output", "report.json",
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        # The executor was constructed with BOTH images.
        _, kwargs = mock_executor_cls.call_args
        assert kwargs["worker_image"] == "workflo-worker:latest"
        assert kwargs["deep_worker_image"] == "myregistry/deep:v1"

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    @patch("workflo_cli.main.generate_sandbox_id", return_value="sandbox-surface-999")
    def test_real_test_run_passes_deep_worker_image_none_to_executor(
        self, mock_id, mock_executor_cls, mock_keypair, runner,
    ):
        """A non-dry-run --test call (no --deep-worker-image) must construct
        SandboxExecutor with deep_worker_image=None — proves the CLI doesn't
        smuggle a default into the executor (the executor owns the default)."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        mock_keypair.return_value = fake_signer

        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult, RunReport, SignedReceipt, TeardownProof,
        )
        from datetime import datetime

        fake_receipt = SignedReceipt(
            sandbox_id="sandbox-surface-999",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="sandbox-surface-999", total=3, passed=3),
            teardown_proof=TeardownProof(
                sandbox_id="sandbox-surface-999",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="sandbox-surface-999",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(fake_receipt)

        fake_result = SandboxRunResult(
            receipt=fake_receipt,
            report=RunReport(sandbox_id="sandbox-surface-999", total=3, passed=3),
            lifecycle_events=[],
            elapsed_seconds=1.0,
            success=True,
        )
        mock_executor = MagicMock()
        mock_executor.run.return_value = fake_result
        mock_executor_cls.return_value = mock_executor

        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test",
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        _, kwargs = mock_executor_cls.call_args
        # The CLI must NOT pre-resolve deep_worker_image to a default — the
        # executor is the source of truth for the default.
        assert kwargs.get("deep_worker_image") is None
        assert kwargs["worker_image"] == "workflo-worker:latest"

    def test_stderr_banner_shows_deep_image_only_for_deep_run(self, runner):
        """The stderr banner must mention 'Deep worker image (selected):'
        ONLY when the auto-switch engages. For a --test run the banner must
        NOT mention the deep image — that's the visible-cue contract."""
        with patch("workflo_cli.main.generate_keypair"), \
             patch("workflo_cli.main.SandboxExecutor") as mock_exec, \
             patch("workflo_cli.main.generate_sandbox_id", return_value="sb"):
            from workflo_executor.executor import SandboxRunResult
            from workflo_schema.sandbox import (
                CanaryCheckResult, RunReport, SignedReceipt, TeardownProof,
            )
            from datetime import datetime, UTC

            fake_receipt = SignedReceipt(
                sandbox_id="sb",
                issued_at=datetime.now(UTC),
                run_report=RunReport(sandbox_id="sb"),
                teardown_proof=TeardownProof(
                    sandbox_id="sb",
                    container_removed=True,
                    filesystem_removed=True,
                    destroyed_at=datetime.now(UTC),
                ),
                canary_check=CanaryCheckResult(
                    sandbox_id="sb",
                    attempted_at=datetime.now(UTC),
                    request_succeeded=False,
                    error="blocked",
                ),
            )
            fake_result = SandboxRunResult(
                receipt=fake_receipt,
                report=RunReport(sandbox_id="sb"),
                lifecycle_events=[],
                elapsed_seconds=0.1,
                success=True,
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = fake_result
            mock_exec.return_value = mock_executor

            with runner.isolated_filesystem():
                surface_out = runner.invoke(cli, [
                    "run", "--repo", "https://github.com/example/repo.git", "--test",
                ]).output
                deep_out = runner.invoke(cli, [
                    "run", "--repo", "https://github.com/example/repo.git", "--deep-test",
                ]).output

        # --test run: no deep image line
        assert "Deep worker image (selected):" not in surface_out
        # --deep-test run: deep image line present, naming the default image
        assert "Deep worker image (selected):" in deep_out
        assert "workflo-worker-deep:latest" in deep_out


class TestCLIConfigDeepWorkerImage:
    """Config-file support for deep_worker_image (round-trips with the flag)."""

    @pytest.fixture(autouse=True)
    def _clean_llm(self, clean_llm_config):
        pass

    def test_config_yaml_provides_deep_worker_image(self, runner, tmp_path):
        """A YAML config with `deep_worker_image: custom:latest` flows through
        to the dry-run plan when --deep-test is also set."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "deep_test: true\n"
            "deep_worker_image: cfg-registry/deep:v2\n",
            encoding="utf-8",
        )
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["deep_worker_image"] == "cfg-registry/deep:v2"
        assert plan["selected_worker_image"] == "cfg-registry/deep:v2"

    def test_cli_flag_overrides_config_deep_worker_image(self, runner, tmp_path):
        """Explicit --deep-worker-image must override config file value
        (same precedence rule as --repo / --timeout / etc.)."""
        config_file = tmp_path / "workflo.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "deep_test: true\n"
            "deep_worker_image: cfg-registry/deep:v2\n",
            encoding="utf-8",
        )
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file),
                "--deep-worker-image", "cli-override/deep:v3",
                "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["deep_worker_image"] == "cli-override/deep:v3"
        assert plan["selected_worker_image"] == "cli-override/deep:v3"


class TestCLIWebWorkerImage:
    """Tests for --web + --start-command/--port + the web auto-switch.

    Phase 3 Track A.3 exit-gate backing. Verifies:
      1. --web --dry-run selects the web image (auto-switch) and carries
         web_config in the plan.
      2. --web WITHOUT --start-command/--port fails fast pre-Docker with
         an actionable UsageError (no workflo.yaml to fall back to for a
         remote repo).
      3. A local file:// repo's workflo.yaml provides the web config
         fallback (contract: CLI flags > workflo.yaml).
      4. The web config reaches the SandboxSpec run_spec env so the
         executor forwards WORKFLO_START_COMMAND/WORKFLO_WEB_PORT into
         the container.
      5. Invalid port is rejected before any Docker work.
      6. deep + web combination is rejected (combined image not built).
    """

    def test_web_dry_run_auto_switches_to_web_image(self, runner):
        """--web --start-command/--port --dry-run: probe_groups contains
        web, selected image is workflo-worker-web:latest, web_config is
        carried in the plan."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--web", "--start-command", "python app.py", "--port", "5000",
                "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert "web" in plan["probe_groups"]
        assert plan["selected_worker_image"] == "workflo-worker-web:latest"
        assert plan["web_config"] == {"start_command": "python app.py", "port": 5000}

    def test_web_without_config_fails_fast(self, runner):
        """--web with no start_command/port (and no local workflo.yaml)
        must fail BEFORE any Docker work with an actionable message."""
        with patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls:
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--web", "--dry-run",
            ])
        assert result.exit_code != 0
        assert "--start-command" in result.output
        assert "--port" in result.output
        mock_executor_cls.assert_not_called()

    def test_local_workflo_yaml_provides_web_config(self, runner, tmp_path):
        """A file:// repo with a workflo.yaml web section supplies the
        start_command/port fallback (CLI flags win when present)."""
        (tmp_path / "workflo.yaml").write_text(
            "web:\n"
            "  start_command: \"python app.py\"\n"
            "  port: 5000\n",
            encoding="utf-8",
        )
        repo_url = f"file://{tmp_path.as_posix()}"
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", repo_url,
                "--web", "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["web_config"] == {"start_command": "python app.py", "port": 5000}

    def test_cli_flags_win_over_local_workflo_yaml(self, runner, tmp_path):
        """CLI flags override local workflo.yaml."""
        (tmp_path / "workflo.yaml").write_text(
            "web:\n"
            "  start_command: \"python app.py\"\n"
            "  port: 5000\n",
            encoding="utf-8",
        )
        repo_url = f"file://{tmp_path.as_posix()}"
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", repo_url,
                "--web", "--start-command", "python cli.py", "--port", "9000",
                "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["web_config"] == {"start_command": "python cli.py", "port": 9000}

    def test_config_file_supports_web_keys(self, runner, tmp_path):
        """The config file may carry web/start_command/port keys."""
        config_file = tmp_path / "cfg.yaml"
        config_file.write_text(
            "repo: https://github.com/example/repo.git\n"
            "web: true\n"
            "start_command: python app.py\n"
            "port: 5000\n",
            encoding="utf-8",
        )
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--config", str(config_file), "--dry-run",
            ])
        assert result.exit_code == 0, result.output
        plan = _parse_plan_json(result.output)
        assert plan["web_config"] == {"start_command": "python app.py", "port": 5000}

    def test_deep_plus_web_combination_rejected(self, runner):
        """Combining a deep tier with --web is not yet supported."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--deep-test", "--web", "--start-command", "python app.py", "--port", "5000",
                "--dry-run",
            ])
        assert result.exit_code != 0
        assert "not supported" in result.output.lower() or "combined" in result.output.lower()

    def test_invalid_port_rejected(self, runner):
        """Invalid port number must be rejected before any Docker work."""
        with patch("workflo_cli.main.SandboxExecutor"):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--web", "--start-command", "python app.py", "--port", "70000",
                "--dry-run",
            ])
        assert result.exit_code != 0
        assert "port" in result.output.lower()


class TestCLIAuthGate:
    """Tests for the authentication gate on workflo run."""

    @patch("workflo_cli.main.generate_keypair")
    @patch("workflo_cli.main.SandboxExecutor")
    def test_run_without_auth_fails_when_publish(self, mock_executor_cls, mock_keypair, runner):
        """--publish without auth must fail."""
        mock_keypair.return_value = MagicMock()
        mock_executor = MagicMock()
        mock_executor.run.return_value = MagicMock(
            success=True, receipt=MagicMock(
                teardown_proof=MagicMock(container_removed=True, filesystem_removed=True),
                canary_check=MagicMock(request_succeeded=False),
                signature="a" * 64,
            ),
            report=MagicMock(passed=1, total=1, failed=0, collection_error=None),
            elapsed_seconds=1.0,
        )
        mock_executor_cls.return_value = mock_executor

        # Override the global auth mock to simulate unauthenticated
        from cortex_auth.session import AuthSession
        fake_auth = MagicMock()
        fake_auth.status.return_value = None
        with patch("cortex_auth.session.AuthSession", return_value=fake_auth):
            result = runner.invoke(cli, [
                "run", "--repo", "https://github.com/example/repo.git",
                "--test", "--publish",
            ])
        assert result.exit_code != 0
        assert "not authenticated" in result.output.lower()

    def test_run_without_auth_succeeds_without_publish(self, runner):
        """Plain --test run without auth should succeed (auth only required for --publish/--via-api)."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from workflo_executor.executor import SandboxRunResult
        from workflo_schema.sandbox import (
            CanaryCheckResult, RunReport, SignedReceipt, TeardownProof,
        )

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )
        with patch("workflo_cli.main.generate_keypair", return_value=fake_signer):
            fake_receipt = SignedReceipt(
                sandbox_id="sandbox-noauth-001",
                issued_at=datetime.now(UTC),
                run_report=RunReport(sandbox_id="sandbox-noauth-001", total=1, passed=1),
                teardown_proof=TeardownProof(
                    sandbox_id="sandbox-noauth-001",
                    container_removed=True,
                    filesystem_removed=True,
                    destroyed_at=datetime.now(UTC),
                ),
                canary_check=CanaryCheckResult(
                    sandbox_id="sandbox-noauth-001",
                    attempted_at=datetime.now(UTC),
                    target_host="https://example.com",
                    request_succeeded=False,
                    error="blocked",
                ),
            )
            fake_signer.sign(fake_receipt)

            fake_result = SandboxRunResult(
                receipt=fake_receipt,
                report=RunReport(sandbox_id="sandbox-noauth-001", total=1, passed=1),
                lifecycle_events=[],
                elapsed_seconds=1.0,
                success=True,
            )

            with patch("workflo_cli.main.generate_keypair", return_value=fake_signer), \
                 patch("workflo_cli.main.SandboxExecutor") as mock_executor_cls:
                mock_executor = MagicMock()
                mock_executor.run.return_value = fake_result
                mock_executor_cls.return_value = mock_executor

                # Override auth to unauthenticated
                fake_auth = MagicMock()
                fake_auth.status.return_value = None
                with patch("cortex_auth.session.AuthSession", return_value=fake_auth):
                    result = runner.invoke(cli, [
                        "run", "--repo", "https://github.com/example/repo.git", "--test",
                    ])

                assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"

    @patch("httpx.Client.post")
    def test_via_api_requires_auth(self, mock_post, runner):
        """--via-api without auth must fail."""
        mock_post.return_value = MagicMock(
            status_code=401,
            json=lambda: {"detail": "Unauthorized"},
            text="Unauthorized"
        )
        result = runner.invoke(cli, [
            "run", "--repo", "https://github.com/example/repo.git",
            "--test", "--via-api", "http://localhost:8000",
        ])
        assert result.exit_code != 0
        assert "not authenticated" in result.output.lower() or "auth" in result.output.lower()


class TestCLIVerify:
    """Tests for `workflo verify` command."""

    @patch("workflo_cli.main.verify_receipt_signature", return_value=True)
    @patch("workflo_cli.main._load_ed25519_pubkey")
    def test_verify_valid_receipt(self, mock_load_key, mock_verify, runner, tmp_path):
        """Valid receipt with matching pubkey passes."""
        from sandbox_isolation.receipt_signer import ReceiptSigner
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from workflo_schema.sandbox import SignedReceipt

        private_key = Ed25519PrivateKey.generate()
        fake_signer = ReceiptSigner(
            private_key=private_key,
            public_key=private_key.public_key(),
        )

        receipt = SignedReceipt(
            sandbox_id="verify-test-001",
            issued_at=datetime.now(UTC),
            run_report=RunReport(sandbox_id="verify-test-001", total=5, passed=5),
            teardown_proof=TeardownProof(
                sandbox_id="verify-test-001",
                container_removed=True,
                filesystem_removed=True,
                destroyed_at=datetime.now(UTC),
            ),
            canary_check=CanaryCheckResult(
                sandbox_id="verify-test-001",
                attempted_at=datetime.now(UTC),
                target_host="https://example.com",
                request_succeeded=False,
                error="blocked",
            ),
        )
        fake_signer.sign(receipt)

        receipt_file = tmp_path / "receipt.json"
        receipt_file.write_text(json.dumps({"receipt": receipt.model_dump(mode="json")}, default=str), encoding="utf-8")

        pubkey_file = tmp_path / "pubkey.pem"
        pubkey_pem = fake_signer.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pubkey_file.write_bytes(pubkey_pem)

        result = runner.invoke(cli, ["verify", "--receipt", str(receipt_file), "--pubkey", str(pubkey_file)])
        assert result.exit_code == 0
        assert "OK" in result.output or "verified" in result.output.lower()


class TestCLIKeygen:
    """Tests for `workflo keygen` command."""

    def test_keygen_outputs_pem_keys(self, runner):
        """keygen outputs PEM-encoded keys."""
        result = runner.invoke(cli, ["keygen"])
        assert result.exit_code == 0
        assert "BEGIN PRIVATE KEY" in result.output
        assert "BEGIN PUBLIC KEY" in result.output
        assert "Fingerprint (SHA-256):" in result.output

    @patch("httpx.Client.post")
    @patch("cortex_auth.session.AuthSession")
    def test_keygen_provision(self, mock_auth_session, mock_post, runner):
        """keygen --provision sends public key to control plane."""
        from cortex_auth.session import AuthSession
        from cortex_auth.scopes import WORKFLO_SCOPES, PRODUCT_CLIENT_IDS

        fake_session = MagicMock()
        fake_session.get_access_token.return_value = "fake-token"
        mock_auth_session.return_value = fake_session

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"key_id": "test-key-id"},
        )

        result = runner.invoke(cli, ["keygen", "--provision", "--device-id", "test-device"])
        assert result.exit_code == 0
        assert "Key provisioned" in result.output


class TestCLIPersistPubkey:
    """The run persists its ephemeral signing pubkey so `verify` can find it."""

    def test_persist_writes_loadable_pubkey(self, tmp_path, monkeypatch):
        from workflo_cli.main import _persist_signing_pubkey
        from sandbox_isolation import generate_keypair

        monkeypatch.setattr(
            "pathlib.Path.home",
            lambda *a, **k: tmp_path,
        )
        signer = generate_keypair()

        _persist_signing_pubkey(signer)

        key_file = tmp_path / ".config" / "workflo" / "keys" / f"{signer.public_key_fingerprint}.pub.pem"
        assert key_file.exists()
        loaded = serialization.load_pem_public_key(key_file.read_bytes())
        assert loaded == signer.public_key

    def test_persist_is_nonfatal_on_bad_signer(self, tmp_path, monkeypatch, capsys):
        from workflo_cli.main import _persist_signing_pubkey

        monkeypatch.setattr("pathlib.Path.home", lambda *a, **k: tmp_path)

        _persist_signing_pubkey(MagicMock())  # must not raise

        assert "warning: could not persist signing pubkey" in capsys.readouterr().err