"""GitHub connector tests — run against real local git repos (file://).

These exercise the ACTUAL git protocol paths the production connector
uses (ls-remote, fetch-by-SHA, pinned checkout) — no mocks. A local
file:// remote speaks the same git protocol the connector uses for
github.com, minus auth.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sandbox_runtime.github_connector import (
    GitConnectorError,
    build_provenance,
    clone_pinned,
    parse_repository_url,
    resolve_ref,
    validate_ref,
)


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def test_parse_https_github_url():
    spec = parse_repository_url("https://github.com/acme/shop")
    assert spec.provider == "github"
    assert spec.repository == "acme/shop"
    assert spec.clone_url == "https://github.com/acme/shop.git"


def test_parse_https_with_dot_git_and_trailing_bits():
    spec = parse_repository_url("https://github.com/acme/shop.git/")
    assert spec.provider == "github"
    assert spec.repository == "acme/shop"


def test_parse_ssh_url():
    spec = parse_repository_url("git@github.com:acme/shop.git")
    assert spec.provider == "github"
    assert spec.repository == "acme/shop"
    assert spec.clone_url == "https://github.com/acme/shop.git"


def test_parse_non_github_host():
    spec = parse_repository_url("https://gitlab.example.com/team/proj")
    assert spec.provider == "git"
    assert spec.host == "gitlab.example.com"


def test_parse_file_url(tmp_path):
    spec = parse_repository_url(f"file://{tmp_path}")
    assert spec.provider == "git"
    assert spec.clone_url == str(tmp_path)


@pytest.mark.parametrize("bad", [
    "", "not-a-url", "https://github.com/", "https://github.com/onlyowner",
])
def test_parse_rejects_bad_urls(bad):
    with pytest.raises(GitConnectorError):
        parse_repository_url(bad)


# ---------------------------------------------------------------------------
# Ref validation
# ---------------------------------------------------------------------------

def test_validate_ref_accepts_branch_tag_sha():
    assert validate_ref("main") == "main"
    assert validate_ref("release/2026-09") == "release/2026-09"
    assert validate_ref("a" * 40) == "a" * 40


@pytest.mark.parametrize("bad", ["-oBad", "--upload-pack=x", "a..b", "", "x y"])
def test_validate_ref_rejects_unsafe(bad):
    with pytest.raises(GitConnectorError):
        validate_ref(bad)


def test_validate_ref_strips_outer_whitespace():
    # Leading/trailing whitespace is normalized, not an attack vector;
    # embedded spaces are the dangerous case (covered above).
    assert validate_ref("  main  ") == "main"


# ---------------------------------------------------------------------------
# Resolve + pinned clone against a real local repo
# ---------------------------------------------------------------------------

def _git(args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def source_repo(tmp_path):
    """A real git repo with two commits on 'main' and a tagged commit."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "t"], repo)

    (repo / "app.py").write_text("print('v1')\n")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "v1"], repo)
    sha_v1 = _git(["rev-parse", "HEAD"], repo)

    (repo / "app.py").write_text("print('v2')\n")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "v2"], repo)
    sha_v2 = _git(["rev-parse", "HEAD"], repo)
    _git(["tag", "v1.0", sha_v1], repo)

    return {"path": repo, "sha_v1": sha_v1, "sha_v2": sha_v2}


def test_resolve_head_on_default_branch(source_repo):
    resolved = resolve_ref(str(source_repo["path"]))
    assert resolved.commit_sha == source_repo["sha_v2"]
    assert resolved.requested_ref is None


def test_resolve_named_branch(source_repo):
    resolved = resolve_ref(str(source_repo["path"]), "main")
    assert resolved.commit_sha == source_repo["sha_v2"]


def test_resolve_tag(source_repo):
    resolved = resolve_ref(str(source_repo["path"]), "v1.0")
    assert resolved.commit_sha == source_repo["sha_v1"]


def test_resolve_full_sha_passthrough(source_repo):
    resolved = resolve_ref(str(source_repo["path"]), source_repo["sha_v1"])
    assert resolved.commit_sha == source_repo["sha_v1"]


def test_resolve_unknown_ref_fails(source_repo):
    with pytest.raises(GitConnectorError):
        resolve_ref(str(source_repo["path"]), "no-such-branch")


def test_clone_pinned_gets_exact_commit(source_repo, tmp_path):
    dest = tmp_path / "clone"
    clone_pinned(str(source_repo["path"]), source_repo["sha_v1"], dest)
    head = _git(["rev-parse", "HEAD"], dest)
    assert head == source_repo["sha_v1"]
    assert (dest / "app.py").read_text() == "print('v1')\n"


def test_clone_pinned_rejects_short_sha(source_repo, tmp_path):
    with pytest.raises(GitConnectorError):
        clone_pinned(str(source_repo["path"]), source_repo["sha_v1"][:7], tmp_path / "x")


def test_clone_pinned_bad_commit_fails(source_repo, tmp_path):
    with pytest.raises(GitConnectorError):
        clone_pinned(str(source_repo["path"]), "0" * 40, tmp_path / "x")


def test_build_provenance_shape(source_repo):
    spec = parse_repository_url(f"file://{source_repo['path']}")
    resolved = resolve_ref(spec.clone_url, "main")
    prov = build_provenance(spec, resolved, snapshot_digest="ab" * 32)
    assert prov["provider"] == "git"
    assert prov["ref"] == "main"
    assert prov["commit"] == source_repo["sha_v2"]
    assert prov["snapshot_digest"] == "ab" * 32
