"""Tests for scripts/ci/check_security_review.py.

Each test builds a throwaway git repo, commits a docs/SECURITY_CRITICAL.md
listing one critical path, then commits work against (or away from) that
path and asserts the gate's verdict. The gate must fail closed and must
have no environment-variable bypass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_security_review.py"

CRITICAL_MD = """# Security-critical paths (owner review required)
# One repo-relative path per line; blank lines and #-comments ignored.
packages/judge
"""


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "docs").mkdir()
    (repo / "docs" / "SECURITY_CRITICAL.md").write_text(CRITICAL_MD, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "S00: baseline")
    return repo


def _commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo: Path, base: str, head: str, extra_env: dict[str, str] | None = None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", base, "--head", head],
        capture_output=True,
        text=True,
        env=env,
    )


def _base_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def test_non_critical_change_passes(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(repo, "S02: touch safe code", {"packages/workflo-utils/src/x.py": "x = 1\n"})
    proc = _run(repo, base, head)
    assert proc.returncode == 0, proc.stderr


def test_critical_change_with_approved_review_passes(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(
        repo,
        "S10: judge hardening",
        {
            "packages/judge/src/verdict.py": "verdict = True\n",
            "docs/reviews/S10.md": "# review\nAPPROVED-BY: owner\n2026-10-27\n",
        },
    )
    proc = _run(repo, base, head)
    assert proc.returncode == 0, proc.stderr


def test_critical_change_without_review_fails(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(repo, "S10: judge change", {"packages/judge/src/verdict.py": "verdict = True\n"})
    proc = _run(repo, base, head)
    assert proc.returncode != 0
    assert "docs/reviews/S10.md" in proc.stderr
    assert "packages/judge/src/verdict.py" in proc.stderr


def test_review_without_approval_line_fails(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(
        repo,
        "S10: judge change",
        {
            "packages/judge/src/verdict.py": "verdict = True\n",
            "docs/reviews/S10.md": "# review pending\n",
        },
    )
    proc = _run(repo, base, head)
    assert proc.returncode != 0
    assert "APPROVED-BY: owner" in proc.stderr


def test_critical_change_in_non_step_commit_fails(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(repo, "refactor: judge internals", {"packages/judge/src/verdict.py": "x = 2\n"})
    proc = _run(repo, base, head)
    assert proc.returncode != 0
    assert "Sxx" in proc.stderr


def test_directory_prefix_critical_path_matches_children(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    # SECURITY_CRITICAL.md lists packages/judge (a directory); a nested file must trip the gate.
    head = _commit(repo, "S11: ledger internals", {"packages/judge/src/deep/nested.py": "y = 3\n"})
    proc = _run(repo, base, head)
    assert proc.returncode != 0


def test_no_environment_variable_bypass(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(repo, "S10: judge change", {"packages/judge/src/verdict.py": "verdict = True\n"})
    for var in ("CHECK_SECURITY_REVIEW_SKIP", "SKIP_SECURITY_REVIEW", "WORKFLO_SKIP_REVIEW"):
        proc = _run(repo, base, head, extra_env={var: "1"})
        assert proc.returncode != 0, f"{var} must not bypass the gate"


def test_clean_range_passes_without_security_file_changes(tmp_path):
    repo = _init_repo(tmp_path)
    base = _base_sha(repo)
    head = _commit(repo, "S03: run service", {"packages/workflo-utils/src/y.py": "y = 2\n"})
    proc = _run(repo, base, head)
    assert proc.returncode == 0, proc.stderr
