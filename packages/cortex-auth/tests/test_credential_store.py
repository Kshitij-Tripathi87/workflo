"""Tests for the file-backed credential store (the secure-store fallback)."""

from pathlib import Path

from cortex_auth.credential_store import FileCredentialStore, get_credential_store


class TestFileCredentialStore:
    def test_set_and_get_round_trip(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        store.set("cortex-labs", "refresh_token", "rt_abc123")
        assert store.get("cortex-labs", "refresh_token") == "rt_abc123"

    def test_get_returns_none_for_missing_key(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        assert store.get("default", "refresh_token") is None

    def test_namespaces_are_isolated(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        store.set("personal", "refresh_token", "rt_one")
        store.set("work", "refresh_token", "rt_two")
        assert store.get("personal", "refresh_token") == "rt_one"
        assert store.get("work", "refresh_token") == "rt_two"

    def test_delete_removes_single_key(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        store.set("default", "refresh_token", "rt_x")
        store.set("default", "access_token", "at_y")
        store.delete("default", "refresh_token")
        assert store.get("default", "refresh_token") is None
        assert store.get("default", "access_token") == "at_y"

    def test_clear_removes_namespace(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        store.set("default", "refresh_token", "rt_x")
        store.set("default", "access_token", "at_y")
        store.clear("default")
        assert store.get("default", "refresh_token") is None
        assert store.get("default", "access_token") is None

    def test_file_permissions_are_0600(self, tmp_path: Path):
        path = tmp_path / "creds.json"
        store = FileCredentialStore(path)
        store.set("default", "refresh_token", "rt_x")
        # On Windows file mode bits are largely symbolic, but POSIX must be 0600.
        import os
        if os.name == "posix":
            mode = path.stat().st_mode & 0o777
            assert mode == 0o600

    def test_corrupt_file_returns_empty(self, tmp_path: Path):
        path = tmp_path / "creds.json"
        path.write_text("not json {")
        store = FileCredentialStore(path)
        assert store.get("default", "refresh_token") is None

    def test_set_overwrites_existing(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        store.set("default", "refresh_token", "rt_old")
        store.set("default", "refresh_token", "rt_new")
        assert store.get("default", "refresh_token") == "rt_new"

    def test_available_is_true(self, tmp_path: Path):
        store = FileCredentialStore(tmp_path / "creds.json")
        assert store.available() is True


class TestGetCredentialStore:
    def test_returns_a_backend(self):
        store = get_credential_store()
        # Whatever the platform, we must get something usable.
        assert store.available() is True
        assert store.backend_name()
