"""Project detection tests (Phase 7)."""

import json

from workflo_utils.detect import detect_project


class TestNodeDetection:
    def test_package_json_sets_node(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "app",
            "scripts": {
                "test": "pnpm test",
                "start": "vite",
            },
            "devDependencies": {"vitest": "^1.0"},
        }))
        (tmp_path / "pnpm-lock.yaml").write_text("lock")

        det = detect_project(tmp_path)
        assert det.language == "nodejs"
        assert det.package_manager == "pnpm"
        assert det.test_command == "pnpm test"
        assert det.start_command == "pnpm start"
        assert det.port is not None

    def test_default_pkg_manager_when_no_lock(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "app", "scripts": {"test": "npm test"}}))
        det = detect_project(tmp_path)
        assert det.package_manager == "npm"

    def test_no_manifest_is_unknown(self, tmp_path):
        det = detect_project(tmp_path)
        assert not det.detected
        assert "package.json" in det.notes[0]


class TestPythonDetection:
    def test_pyproject_and_pytest(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='app'\n")
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        det = detect_project(tmp_path)
        assert det.language == "python"
        assert det.test_command == "pytest"

    def test_framework_detection(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0\n")
        (tmp_path / "pyproject.toml").write_text("")
        det = detect_project(tmp_path)
        assert det.framework == "flask"
        assert det.start_command is not None


class TestRobustness:
    def test_non_directory(self, tmp_path):
        det = detect_project(tmp_path / "nonexistent")
        assert not det.detected

    def test_package_json_unreadable(self, tmp_path):
        (tmp_path / "package.json").write_text("not json at all {{{")
        det = detect_project(tmp_path)
        assert det.language == "nodejs"
        assert det.test_command is None  # notes explain why
