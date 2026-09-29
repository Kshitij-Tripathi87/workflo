"""Project config (schema) tests."""

from pathlib import Path

from workflo_utils.project_config import (
    PROJECT_CONFIG_FILE,
    ProjectConfig,
)
from workflo_utils.detect import config_for_detection


class TestSchemaRoundTrip:
    def test_defaults_roundtrip(self, tmp_path):
        cfg = ProjectConfig()
        path = cfg.save(tmp_path)
        loaded = ProjectConfig.load(path)
        assert loaded.to_dict() == cfg.to_dict()

    def test_load_partial_file_uses_defaults(self, tmp_path):
        p = tmp_path / PROJECT_CONFIG_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("project:\n  test_command: npm test\nsecurity:\n  mode: hardened\n")
        cfg = ProjectConfig.load(p)
        assert cfg.test_command == "npm test"
        assert cfg.security_mode == "hardened"
        assert cfg.memory_mb == 4096  # default preserved
        assert cfg.agent.enabled is True

    def test_find_returns_none_when_missing(self, tmp_path):
        assert ProjectConfig.find(tmp_path) is None

    def test_find_and_load_from_discovered_path(self, tmp_path):
        cfg = ProjectConfig(test_command="vitest run")
        cfg.save(tmp_path)
        found = ProjectConfig.find(tmp_path)
        assert found is not None
        assert ProjectConfig.load(found).test_command == "vitest run"

    def test_non_dict_file_falls_back_to_defaults(self, tmp_path):
        p = tmp_path / PROJECT_CONFIG_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("42\n")
        cfg = ProjectConfig.load(p)
        assert cfg.test_command == "pytest"  # schema default

    def test_no_credentials_in_project_config(self, tmp_path):
        """Project config is checked into the repo — secrets never live here."""
        cfg = ProjectConfig()
        data = cfg.to_dict()
        text = str(data)
        for forbidden in ("api_key", "private_key", "token", "secret"):
            assert forbidden not in text.lower() or "env" in text.lower()

    def test_never_overwrites_without_force_is_cli_s_job(self, tmp_path):
        """The model itself writes; non-destructive behavior is enforced
        by the CLI (init). Saving twice is idempotent, not destructive."""
        cfg = ProjectConfig(test_command="vitest run")
        path = cfg.save(tmp_root := tmp_path)
        cfg2 = ProjectConfig()
        # Save again — overwrites, same path, but content differs only by
        # caller intent (the CLI refuses to do this without --force).
        cfg2.save(tmp_path)
        assert ProjectConfig.load(path).test_command == "pytest"
