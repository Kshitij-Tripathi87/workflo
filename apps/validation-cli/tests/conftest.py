"""Pytest fixtures shared by validation-cli tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_work_dir():
    """Provide a temporary working directory; auto-cleaned after test."""
    d = Path(tempfile.mkdtemp(prefix="vphase2-test-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def local_git_repo(temp_work_dir):
    """Create a local git repo with one commit + main branch.

    Required because clone_repo() and resolve_baseline() invoke real git
    commands and rely on a HEAD + origin/main history.
    """
    repo = temp_work_dir / "source_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main", "-q", str(repo)], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=repo, check=True)

    # Need a real origin for merge-base to work. Use a bare clone as the
    # origin and push main to it so origin/main exists.
    bare = temp_work_dir / "origin.git"
    subprocess.run(["git", "clone", "--bare", "-q", str(repo), str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=repo, check=True)
    subprocess.run(["git", "branch", "--set-upstream-to=origin/main", "main"],
                   cwd=repo, check=True)

    return repo
