"""Local Git object materialization for the sealed development profile."""

from __future__ import annotations

import os
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

from workflo_schema.contracts.canonical import sha256_digest
from workflo_schema.dev_check import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_FILES,
    LocalSnapshot,
    SnapshotFile,
    validate_revision,
    validate_source_path,
)

from sandbox_runtime.snapshot import SECRET_PATTERNS


class SourceRejected(ValueError):
    """The requested revision cannot be admitted by this profile."""


def _excluded(path: str) -> bool:
    parts = path.split("/")
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]
    return any(
        candidate.startswith(pattern) if pattern.endswith("/") else fnmatchcase(candidate, pattern)
        for pattern in SECRET_PATTERNS
        for candidate in suffixes
    )


def materialize_pinned_source(repo: Path, commit: str, dest: Path) -> LocalSnapshot:
    """Read tracked blobs, never a checkout, smudge filter, hook or remote fetch.

    The local object database is a developer-controlled input. Ignore Git
    environment overrides and replacement refs; never copy .git into the guest.
    """
    validate_revision(commit)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "",
            "GIT_NO_LAZY_FETCH": "1",
        }
    )

    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), *args],
            env=env,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
        if result.returncode:
            raise SourceRejected(
                f"could not read pinned Git revision ({args[0]}); fetch or verify it locally first"
            )
        return result.stdout

    if git("rev-parse", "--verify", f"{commit}^{{commit}}").strip() != commit.encode("ascii"):
        raise SourceRejected("revision does not name the exact commit object")
    listing = git("ls-tree", "-rlz", "--full-tree", commit)
    files = []
    bytes_total = 0
    for record in listing.split(b"\0")[:-1]:
        header, path_raw = record.split(b"\t", 1)
        mode, kind, oid, size = header.decode("ascii").split()
        path = validate_source_path(path_raw.decode("utf-8"))
        if mode not in ("100644", "100755") or kind != "blob":
            raise SourceRejected("development snapshots do not allow symlinks or submodules")
        if _excluded(path):
            continue
        bytes_total += int(size)
        if len(files) >= MAX_SOURCE_FILES or bytes_total > MAX_SOURCE_BYTES:
            raise SourceRejected("pinned snapshot exceeds the development profile's size limits")
        files.append((path, mode, oid, int(size)))

    dest.mkdir(parents=True, exist_ok=False)
    manifest = []
    for path, mode, oid, size in sorted(files):
        data = git("cat-file", "blob", oid)
        if len(data) != size:
            raise SourceRejected("Git blob size differs from the pinned tree")
        output = dest / path
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as file:
            file.write(data)
        output.chmod(0o755 if mode == "100755" else 0o644)
        manifest.append(
            SnapshotFile(path=path, sha256=sha256_digest(data), size_bytes=size, mode=mode)
        )
    return LocalSnapshot(commit=commit, files=tuple(manifest))
