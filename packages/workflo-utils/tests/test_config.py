import tempfile
import os
from pathlib import Path

import pytest

from workflo_utils.config import load_config, save_config, get_config_value


class TestSaveAndLoadConfig:
    def test_round_trip_preserves_data(self):
        original = {"database": {"host": "localhost", "port": 5432}, "debug": True}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config(original, path)
            loaded = load_config(path)
        assert loaded == original

    def test_load_returns_empty_dict_for_missing_file(self):
        result = load_config(Path("/nonexistent/path/config.yaml"))
        assert result == {}

    def test_load_returns_empty_dict_for_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.yaml"
            path.write_text("")
            result = load_config(path)
        assert result == {}

    def test_save_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b" / "config.yaml"
            save_config({"key": "val"}, path)
            assert path.exists()
            assert load_config(path) == {"key": "val"}


class TestGetConfigValue:
    def test_top_level_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config({"app_name": "shield"}, path)
            assert get_config_value("app_name", path=path) == "shield"

    def test_nested_dot_notation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config({"db": {"host": "pg.internal", "port": 5432}}, path)
            assert get_config_value("db.host", path=path) == "pg.internal"
            assert get_config_value("db.port", path=path) == 5432

    def test_default_value_when_key_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config({}, path)
        assert get_config_value("missing.key", default="fallback", path=path) == "fallback"

    def test_default_value_when_intermediate_is_not_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config({"flat": 42}, path)
        assert get_config_value("flat.nothing", default=0, path=path) == 0

    def test_nonexistent_file_returns_default(self):
        result = get_config_value("any.key", default="absent", path=Path("/nonexistent.yaml"))
        assert result == "absent"

    def test_none_value_in_config_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config({"nullable": None}, path)
        assert get_config_value("nullable", default="safe", path=path) == "safe"