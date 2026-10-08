"""`workflo init` + `workflo doctor` — CLI-level tests."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from workflo_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _node_project(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "demo-app",
        "scripts": {
            "test": "vitest run",
            "dev": "vite",
            "start": "node server.js",
        },
        "devDependencies": {"vitest": "^2.0"},
    }))
    (tmp_path / "package-lock.json").write_text("{}")
    return tmp_path


def _python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\ndependencies = ['pytest']\n"
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    return tmp_path


class TestInit:
    def test_node_project_detected(self, runner: CliRunner, tmp_path):
        _node_project(tmp_path)
        result = runner.invoke(cli, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "nodejs" in result.output
        assert "npm detected" in result.output or "npm" in result.output
        assert (tmp_path / ".workflo" / "config.yaml").exists()
        assert (tmp_path / ".workflo" / "policies.yaml").exists()

    def test_python_project_detected(self, runner: CliRunner, tmp_path):
        _python_project(tmp_path)
        result = runner.invoke(cli, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "python" in result.output
        assert (tmp_path / ".workflo" / "config.yaml").exists()

    def test_init_is_non_destructive(self, runner: CliRunner, tmp_path):
        _node_project(tmp_path)
        assert runner.invoke(cli, ["init", "--path", str(tmp_path)]).exit_code == 0
        original = (tmp_path / ".workflo" / "config.yaml").read_text()
        (tmp_path / ".workflo" / "config.yaml").write_text("custom: marker\n")
        result = runner.invoke(cli, ["init", "--path", str(tmp_path)])
        assert result.exit_code != 0
        # The custom file must be untouched
        assert (tmp_path / ".workflo" / "config.yaml").read_text() == "custom: marker\n"

    def test_init_force_overwrites(self, runner: CliRunner, tmp_path):
        _node_project(tmp_path)
        assert runner.invoke(cli, ["init", "--path", str(tmp_path)]).exit_code == 0
        result = runner.invoke(cli, ["init", "--path", str(tmp_path), "--force"])
        assert result.exit_code == 0

    def test_init_on_empty_dir(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "detected" in result.output

    def test_init_never_touches_source(self, runner: CliRunner, tmp_path):
        _node_project(tmp_path)
        before = (tmp_path / "package.json").read_text()
        runner.invoke(cli, ["init", "--path", str(tmp_path)])
        assert (tmp_path / "package.json").read_text() == before


class TestDoctor:
    def test_doctor_reports_sections(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["doctor", "--path", str(tmp_path)])
        assert "Workflo Doctor" in result.output
        for section in ("Host", "Sandbox", "Project", "AI", "Signing"):
            assert section in result.output

    def test_doctor_exit_code_is_zero_or_one(self, runner: CliRunner, tmp_path):
        # Doctor must NEVER throw opaque exceptions: 0 ready, 1 not.
        result = runner.invoke(cli, ["doctor", "--path", str(tmp_path)])
        assert result.exit_code in (0, 1)

    def test_doctor_reports_status_line(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["doctor", "--path", str(tmp_path)])
        assert "STATUS:" in result.output

    def test_doctor_with_project_config(self, runner: CliRunner, tmp_path):
        runner.invoke(cli, ["init", "--path", str(tmp_path)])
        result = runner.invoke(cli, ["doctor", "--path", str(tmp_path)])
        assert "config file" in result.output.lower()
