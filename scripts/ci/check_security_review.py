#!/usr/bin/env python3
"""Security-review gate: fail closed on unreviewed changes to critical paths.

Rule (docs/review-checklist.md, tasks/S01.md): a commit that touches a path
listed in docs/SECURITY_CRITICAL.md must be a step commit whose subject
starts with the step id (e.g. ``S06: ...``) and must contain
``docs/reviews/<step>.md`` carrying the exact line ``APPROVED-BY: owner``.

There is deliberately no environment-variable or flag bypass: if this
script runs, the rule applies.

Usage:
    python scripts/ci/check_security_review.py --base <sha> [--head <sha=HEAD>]
    python scripts/ci/check_security_review.py --repo <path> --base <sha> --head <sha>

Exit codes: 0 = clean, 1 = violation, 2 = setup/usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

APPROVAL_LINE = "APPROVED-BY: owner"
STEP_RE = re.compile(r"^(S\d+)")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def load_critical_paths(repo: Path) -> list[str]:
    critical_file = repo / "docs" / "SECURITY_CRITICAL.md"
    if not critical_file.exists():
        raise RuntimeError(f"missing {critical_file.relative_to(repo)} — the gate cannot run without it")
    paths: list[str] = []
    for raw in critical_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line.rstrip("/").replace("\\", "/"))
    if not paths:
        raise RuntimeError("docs/SECURITY_CRITICAL.md lists no paths — refusing to no-op the gate")
    return paths


def is_critical(path: str, critical: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized == c or normalized.startswith(c + "/") for c in critical)


def commits_in_range(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    out = _git(repo, "log", "--format=%H%x00%s", "--no-merges", f"{base}..{head}")
    commits: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, subject = line.split("\x00", 1)
        commits.append((sha, subject))
    return list(reversed(commits))


def changed_files(repo: Path, sha: str) -> list[str]:
    out = _git(repo, "show", "--name-only", "--format=", sha)
    return [line for line in out.splitlines() if line.strip()]


def review_ok(repo: Path, sha: str, step_id: str) -> tuple[bool, str]:
    rel = f"docs/reviews/{step_id}.md"
    try:
        content = _git(repo, "show", f"{sha}:{rel}")
    except RuntimeError:
        return False, f"{rel} not found at commit {sha[:12]}"
    if APPROVAL_LINE not in content:
        return False, f"{rel} at {sha[:12]} lacks the line '{APPROVAL_LINE}'"
    return True, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=None, help="repo root (default: auto-detect from cwd)")
    parser.add_argument("--base", required=True, help="base commit of the range under review")
    parser.add_argument("--head", default="HEAD", help="head commit of the range (default: HEAD)")
    args = parser.parse_args(argv)

    try:
        if args.repo:
            repo = Path(args.repo).resolve()
        else:
            repo = Path(
                _git(Path.cwd(), "rev-parse", "--show-toplevel").strip()
            ).resolve()
        critical = load_critical_paths(repo)
        commits = commits_in_range(repo, args.base, args.head)
    except RuntimeError as exc:
        print(f"security-review-gate: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for sha, subject in commits:
        files = changed_files(repo, sha)
        touched = [f for f in files if is_critical(f, critical)]
        if not touched:
            continue
        match = STEP_RE.match(subject)
        if not match:
            failures.append(
                f"commit {sha[:12]} '{subject}' touches security-critical paths but its subject "
                f"does not start with a step id (Sxx): {', '.join(touched)}"
            )
            continue
        step_id = match.group(1)
        ok, reason = review_ok(repo, sha, step_id)
        if not ok:
            failures.append(
                f"commit {sha[:12]} '{subject}' touches security-critical paths "
                f"({', '.join(touched)}): {reason}"
            )

    if failures:
        print("security-review-gate: FAILED — owner review required", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "Add docs/reviews/<Sxx>.md with the line 'APPROVED-BY: owner' to the step commit, "
            "or rework the commit so it does not touch security-critical paths.",
            file=sys.stderr,
        )
        return 1

    print(f"security-review-gate: OK ({len(commits)} commits checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
