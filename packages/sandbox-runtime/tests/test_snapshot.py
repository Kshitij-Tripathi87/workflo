"""Tests for repository snapshotting."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sandbox_runtime.snapshot import create_snapshot, SnapshotConfig


def test_create_snapshot_basic(tmp_path):
    # Create a fake git repo
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file1.py").write_text("print('hello')")
    (repo / "file2.txt").write_text("content")

    dest = tmp_path / "workspace" / "repo"

    # Mock git ls-files
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="file1.py\0file2.txt\0",
            returncode=0
        )

        config = SnapshotConfig(repo_path=repo, sandbox_id="test-123", dest_dir=dest)
        result = create_snapshot(config)

        assert result.files == 2
        assert result.tree_sha256 is not None
        assert len(result.manifest) == 2

        # Files were COPIED to the destination
        assert (dest / "file1.py").read_text() == "print('hello')"
        assert (dest / "file2.txt").read_text() == "content"


def test_create_snapshot_excludes_secrets(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file1.py").write_text("print('hello')")
    (repo / ".env").write_text("SECRET=123")
    (repo / "id_rsa").write_text("private key")

    dest = tmp_path / "workspace" / "repo"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="file1.py\0.env\0id_rsa\0",
            returncode=0
        )

        config = SnapshotConfig(repo_path=repo, sandbox_id="test-123", dest_dir=dest)
        result = create_snapshot(config)

        assert result.files == 1  # Only file1.py
        assert ".env" in result.excluded
        assert "id_rsa" in result.excluded
        assert len(result.secret_exclusion_report) == 2

        # Secrets never reach the snapshot
        assert not (dest / ".env").exists()
        assert not (dest / "id_rsa").exists()


def test_snapshot_manifest_written_to_dest_not_source(tmp_path):
    """The manifest must land in the SNAPSHOT — the user's repo is never
    mutated."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file1.py").write_text("print('hello')")

    dest = tmp_path / "workspace" / "repo"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="file1.py\0",
            returncode=0
        )

        config = SnapshotConfig(repo_path=repo, sandbox_id="test-123", dest_dir=dest)
        result = create_snapshot(config)

        manifest_path = dest / ".workflo_manifest.json"
        assert manifest_path.exists()
        assert not (repo / ".workflo_manifest.json").exists()

        import json
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["tree_sha256"] == result.tree_sha256
        assert manifest["files"] == 1


def test_snapshot_in_place_when_no_dest(tmp_path):
    """dest_dir=None snapshots in place (run-local clone case)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file1.py").write_text("print('hello')")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="file1.py\0",
            returncode=0
        )

        config = SnapshotConfig(repo_path=repo, sandbox_id="test-123")
        result = create_snapshot(config)

        assert result.files == 1
        assert (repo / ".workflo_manifest.json").exists()
