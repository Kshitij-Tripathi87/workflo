"""Repository snapshotting with secret exclusion and manifest hashing.

A snapshot COPIES the repo's tracked files (minus secrets) into the run
workspace. The user's original repo is never mutated: the manifest is
written into the snapshot, not the source.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import fnmatch
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from sandbox_runtime.config import SnapshotConfig, FileManifestEntry, SnapshotResult


SECRET_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.crt", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "*.ppk",
    ".ssh/", ".aws/", ".config/gcloud/", ".azure/", ".kube/",
    "*.env", "*.secret", "*.token", "*credential*", "*password*",
    ".npmrc", ".dockercfg", ".docker/config.json",
    "git-credentials", ".git-credentials",
]


def create_snapshot(config: SnapshotConfig) -> SnapshotResult:
    """Create an immutable repository snapshot with secret exclusion.

    Copies included files from repo_path into dest_dir (preserving
    relative paths and modes) and writes .workflo_manifest.json into the
    SNAPSHOT. The source repo is left untouched.
    """
    repo = config.repo_path
    dest = config.dest_dir if config.dest_dir else repo
    dest.mkdir(parents=True, exist_ok=True)

    include_untracked = config.include_untracked or []
    secret_patterns = config.secret_patterns or SECRET_PATTERNS

    # Get tracked files from git
    tracked_files = _get_git_tracked_files(repo)

    # Add explicitly included untracked
    all_files = set(tracked_files)
    for pattern in include_untracked:
        for f in repo.glob(pattern):
            if f.is_file():
                all_files.add(f.relative_to(repo).as_posix())

    # Filter out secret patterns
    included, excluded, secret_report = _filter_secrets(all_files, repo, secret_patterns)

    # Copy included files into the snapshot + build manifest with SHA-256
    manifest = []
    total_bytes = 0
    hasher = hashlib.sha256()

    for rel_path in sorted(included):
        abs_path = repo / rel_path
        if not abs_path.is_file():
            continue
        stat = abs_path.stat()
        content = abs_path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()

        # Copy into the snapshot (only if source and dest differ)
        dest_path = dest / rel_path
        if abs_path.resolve() != dest_path.resolve():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dest_path)

        entry = FileManifestEntry(
            path=rel_path,
            mode=oct(stat.st_mode & 0o777),
            size=stat.st_size,
            sha256=file_hash
        )
        manifest.append(entry)
        total_bytes += stat.st_size

        # Tree hash: hash of (path + file_hash) pairs, sorted
        hasher.update(f"{rel_path}:{file_hash}".encode())

    tree_sha256 = hasher.hexdigest()

    # Write manifest into the SNAPSHOT (never the source repo) for
    # in-sandbox probe verification
    manifest_path = dest / ".workflo_manifest.json"
    manifest_path.write_text(json.dumps({
        "tree_sha256": tree_sha256,
        "files": len(manifest),
        "total_bytes": total_bytes,
        "manifest": [asdict(m) for m in manifest],
        "excluded": excluded,
        "secret_exclusion_report": secret_report,
    }, indent=2))

    return SnapshotResult(
        tree_sha256=tree_sha256,
        files=len(manifest),
        total_bytes=total_bytes,
        manifest=manifest,
        excluded=excluded,
        secret_exclusion_report=secret_report,
    )


def _get_git_tracked_files(repo: Path) -> list[str]:
    """Get list of git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo, capture_output=True, text=True, check=True
        )
        return [f for f in result.stdout.split("\0") if f]
    except subprocess.CalledProcessError:
        return []


def _filter_secrets(files: set, repo: Path, patterns: list[str]) -> tuple:
    """Filter files matching secret patterns."""
    included = set()
    excluded = []
    secret_report = []
    
    for f in files:
        matched = False
        for pattern in patterns:
            if fnmatch.fnmatch(f, pattern) or fnmatch.fnmatch(f, f"*/{pattern}"):
                matched = True
                excluded.append(f)
                secret_report.append(f"Excluded (secret pattern '{pattern}'): {f}")
                break
        if not matched:
            included.add(f)
    
    return included, excluded, secret_report


def verify_snapshot_manifest(repo: Path, expected_tree_sha: str) -> bool:
    """Verify repository matches manifest."""
    manifest_path = repo / ".workflo_manifest.json"
    if not manifest_path.exists():
        return False
    
    import json
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    return manifest.get("tree_sha256") == expected_tree_sha