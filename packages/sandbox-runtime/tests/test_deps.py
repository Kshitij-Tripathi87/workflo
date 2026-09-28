"""Tests for dependency resolution."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sandbox_runtime.deps import (
    resolve_dependencies, DepConfig, DepMode, _generate_cache_manifest
)


def test_resolve_preflight_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("requests==2.28.0\n")
    
    config = DepConfig(
        mode=DepMode.PREFLIGHT_CACHE,
        repo_path=repo,
        cache_dir=tmp_path / "cache"
    )
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        result = resolve_dependencies(config)
        
        assert result.mode == DepMode.PREFLIGHT_CACHE
        assert result.network_policy == "user-approved"
        assert result.resolved is True
        assert result.cache_manifest_sha256 is not None


def test_resolve_vendor_cache(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = repo / "vendor"
    vendor.mkdir()
    (vendor / "requests-2.28.0.tar.gz").write_bytes(b"fake package")

    config = DepConfig(
        mode=DepMode.VENDOR_CACHE,
        repo_path=repo,
        cache_dir=tmp_path / "cache"
    )

    result = resolve_dependencies(config)

    assert result.mode == DepMode.VENDOR_CACHE
    assert result.network_policy == "none"
    assert result.resolved is True


def test_resolve_vendor_cache_no_deps_repo(tmp_path):
    """A repo with no lockfile and no vendor/ has nothing to vendor —
    the sealed run is self-contained and must resolve trivially."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_x.py").write_text("def test_ok(): pass")

    config = DepConfig(
        mode=DepMode.VENDOR_CACHE,
        repo_path=repo,
        cache_dir=tmp_path / "cache"
    )

    result = resolve_dependencies(config)

    assert result.mode == DepMode.VENDOR_CACHE
    assert result.network_policy == "none"
    assert result.resolved is True
    assert result.lockfile_sha256 is None


def test_resolve_vendor_cache_lockfile_without_vendor_fails(tmp_path):
    """A lockfile without a vendored cache is a real error: deps are
    missing for a sealed run."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("requests==2.28.0\n")

    config = DepConfig(
        mode=DepMode.VENDOR_CACHE,
        repo_path=repo,
        cache_dir=tmp_path / "cache"
    )

    with pytest.raises(RuntimeError, match="vendor"):
        resolve_dependencies(config)


def test_generate_cache_manifest(tmp_path):
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "subdir").mkdir(exist_ok=True)
    (tmp_path / "subdir" / "file2.txt").write_text("content2")
    (tmp_path / "subdir").mkdir(exist_ok=True)
    
    manifest = _generate_cache_manifest(tmp_path)
    
    assert len(manifest) == 64  # SHA256 hex


def test_find_lockfile(tmp_path):
    from sandbox_runtime.deps import _find_lockfile
    
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("requests==2.28.0")
    
    lockfile = _find_lockfile(repo, None)
    
    assert lockfile is not None
    assert lockfile.name == "requirements.txt"