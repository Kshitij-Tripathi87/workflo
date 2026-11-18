"""Git object acquisition does not use HEAD, dirty changes, or replacement refs."""

from __future__ import annotations

import subprocess

import pytest
from sandbox_runtime.pinned_source import SourceRejected, materialize_pinned_source


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    git("init", "-q", "--template=", "--object-format=sha1")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@workflo.invalid")
    return repo, git


def test_snapshot_reads_only_pinned_blobs(repository, tmp_path, monkeypatch):
    repo, git = repository
    (repo / "checks.py").write_text("original\n")
    (repo / ".aws").mkdir()
    (repo / ".aws" / "local-settings").write_text("should be excluded\n")
    git("add", "--", "checks.py", ".aws/local-settings")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")
    (repo / "checks.py").write_text("candidate\n")
    git("commit", "-qam", "candidate")
    candidate = git("rev-parse", "HEAD")
    git("replace", baseline, candidate)
    (repo / "checks.py").write_text("dirty worktree\n")
    (repo / "extra.py").write_text("untracked\n")

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    first = materialize_pinned_source(repo, baseline, tmp_path / "one")
    second = materialize_pinned_source(repo, candidate, tmp_path / "two")
    assert first.commit == baseline and second.commit == candidate
    assert first.digest() != second.digest()
    assert [file.path for file in first.files] == ["checks.py"]
    assert (tmp_path / "one/checks.py").read_text() == "original\n"
    assert (tmp_path / "two/checks.py").read_text() == "candidate\n"
    assert (repo / "checks.py").read_text() == "dirty worktree\n"


def test_snapshot_rejects_source_symlinks_before_copy(repository, tmp_path):
    repo, git = repository
    if git("config", "--default", "true", "--type=bool", "--get", "core.symlinks") == "false":
        pytest.skip("Git cannot store symlinks on this filesystem")
    (repo / "linked").symlink_to(tmp_path / "private-data")
    git("add", "--", "linked")
    git("commit", "-qm", "symlink fixture")
    dest = tmp_path / "snapshot"
    with pytest.raises(SourceRejected, match="symlinks or submodules"):
        materialize_pinned_source(repo, git("rev-parse", "HEAD"), dest)
    assert not dest.exists()


def test_pin_must_name_a_commit_not_an_annotated_tag(repository, tmp_path):
    repo, git = repository
    (repo / "checks.py").write_text("fixture\n")
    git("add", "--", "checks.py")
    git("commit", "-qm", "baseline")
    git("tag", "-a", "v1", "-m", "annotated")
    with pytest.raises(SourceRejected, match="exact commit"):
        materialize_pinned_source(repo, git("rev-parse", "v1"), tmp_path / "snapshot")
