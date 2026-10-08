"""GitHub/git repository connector — ref resolution and pinned clones.

Turns a loose user input (``https://github.com/org/repo``, optional ref)
into pinned, receipt-grade provenance BEFORE anything enters the sandbox:

    repo URL
      -> parse (provider, owner/name, clone URL)
      -> resolve ref -> exact 40-char commit SHA   (git ls-remote)
      -> clone pinned at that commit
      -> provenance dict for the receipt

Why resolve before cloning: a branch ref is a MOVING target. A receipt
that says "we tested main" proves nothing about which code ran. The
resolved commit SHA + the snapshot tree digest pin the exact bytes.

Security notes:
  - Arguments are passed as argv lists (no shell=True anywhere).
  - ref values are validated before touching the network so a hostile ref
    can't become a git option (``--upload-pack`` injection).
  - clone/fetch target paths are always run-local staging directories.

Standard library + the git CLI only; no GitHub API token needed for
public repos (ls-remote/fetch speak git protocol, not REST).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# https://github.com/owner/repo(.git)(/anything) | git@github.com:owner/repo(.git)
_HTTPS_RE = re.compile(
    r"^https?://(?P<host>[^/]+)/(?P<owner>[^/]+)/(?P<repo>[^/#?]+?)(?:\.git)?/?(?:[#?].*)?$",
    re.IGNORECASE,
)
_SSH_RE = re.compile(
    r"^git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>[^/#?]+?)(?:\.git)?$",
    re.IGNORECASE,
)

_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
# Safe ref names: alnum plus ./_- and / (branch paths). No spaces, no
# leading '-', no '..', no control chars — the ref is interpolated into
# git argv, never a shell, but we also refuse anything git could parse
# as an option.
_SAFE_REF_RE = re.compile(r"^(?!-)[A-Za-z0-9._][A-Za-z0-9._/-]{0,199}$")

MAX_URL_LEN = 2048
DEFAULT_LS_REMOTE_TIMEOUT = 60
DEFAULT_CLONE_TIMEOUT = 300


class GitConnectorError(Exception):
    """Any git-protocol failure. Carries a human-readable stage note."""


@dataclass(frozen=True)
class RepoSpec:
    """A parsed repository URL."""
    provider: str          # "github" | "git"
    host: str
    owner: str
    name: str
    clone_url: str         # canonical clone URL actually used
    original_url: str

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class ResolvedRef:
    """The exact commit a ref pointed at when the run resolved it."""
    requested_ref: Optional[str]   # None = remote default branch
    ref_name: str                  # the concrete ref resolved (branch/tag/sha)
    commit_sha: str                # 40-char hex


def parse_repository_url(url: str) -> RepoSpec:
    """Parse a git URL into provider/owner/name.

    file:// URLs pass through as provider='git' with the local path as the
    clone source (used by tests and by local fixtures); anything else must
    look like https/git@. Raises GitConnectorError on unparseable input.
    """
    url = (url or "").strip()
    if not url:
        raise GitConnectorError("empty repository URL")
    if len(url) > MAX_URL_LEN:
        raise GitConnectorError(f"repository URL too long ({len(url)} > {MAX_URL_LEN})")

    if url.lower().startswith("file://"):
        path = url[len("file://"):]
        name = Path(path).name or "local-repo"
        return RepoSpec("git", "local", "local", name, path, url)

    match = _SSH_RE.match(url)
    if match:
        host = match.group("host").lower()
        owner = match.group("owner")
        name = match.group("repo")
    else:
        match = _HTTPS_RE.match(url)
        if not match:
            raise GitConnectorError(
                f"unrecognized repository URL: {url!r} "
                "(expected https://host/owner/repo or git@host:owner/repo)"
            )
        host = match.group("host").lower()
        owner = match.group("owner")
        name = match.group("repo")

    provider = "github" if host.endswith("github.com") else "git"
    if host == "github.com":
        clone_url = f"https://github.com/{owner}/{name}.git"
    else:
        clone_url = url  # already canonical enough for non-GitHub hosts
    return RepoSpec(provider, host, owner, name, clone_url, url)


def validate_ref(ref: str) -> str:
    """Validate a user-supplied ref (branch, tag, or full SHA)."""
    ref = (ref or "").strip()
    if not ref:
        raise GitConnectorError("empty ref")
    if _FULL_SHA_RE.match(ref):
        return ref.lower()
    if not _SAFE_REF_RE.match(ref) or ".." in ref or ref.endswith("/"):
        raise GitConnectorError(f"unsafe or invalid ref: {ref!r}")
    return ref


def resolve_ref(clone_url: str, ref: Optional[str] = None,
                timeout: int = DEFAULT_LS_REMOTE_TIMEOUT) -> ResolvedRef:
    """Resolve a ref to an exact commit SHA without cloning (ls-remote).

    Order of attempts:
      1. the exact ref            -> refs/heads/<ref>, refs/tags/<ref>, <ref>
      2. full SHA passthrough     -> returned as-is (verified at fetch time)
      3. no ref                   -> HEAD (remote default branch)

    Raises GitConnectorError when nothing resolves.
    """
    if ref:
        ref = validate_ref(ref)
        if _FULL_SHA_RE.match(ref):
            # A full SHA is already pinned; ls-remote can't list arbitrary
            # SHAs on all servers — fetch validates it at clone time.
            return ResolvedRef(requested_ref=ref, ref_name=ref, commit_sha=ref.lower())
        patterns = [ref, f"refs/heads/{ref}", f"refs/tags/{ref}"]
    else:
        patterns = ["HEAD"]

    for pattern in patterns:
        result = _git(["ls-remote", clone_url, pattern], timeout=timeout)
        for line in result.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            sha, name = parts
            if name == pattern and _FULL_SHA_RE.match(sha):
                return ResolvedRef(
                    requested_ref=ref,
                    ref_name=ref if ref else "HEAD",
                    commit_sha=sha.lower(),
                )
    raise GitConnectorError(
        f"could not resolve ref {ref!r} on {clone_url}" if ref
        else f"could not resolve HEAD on {clone_url}"
    )


def clone_pinned(clone_url: str, commit_sha: str, dest_dir: Path,
                 timeout: int = DEFAULT_CLONE_TIMEOUT) -> None:
    """Clone exactly one commit into dest_dir (no checkout of anything else).

    Fast path: shallow fetch of the pinned SHA into a fresh repo
    (git init + fetch --depth 1 <sha> + checkout FETCH_HEAD). Servers that
    forbid fetch-by-SHA fall back to a full clone + checkout.

    dest_dir must not exist yet (created here).
    """
    commit_sha = commit_sha.lower()
    if not _FULL_SHA_RE.match(commit_sha):
        raise GitConnectorError(f"clone_pinned requires a full SHA, got {commit_sha!r}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=False)

    def _git_in(args, **kw):
        return _git(args, cwd=dest_dir, timeout=timeout, **kw)

    _git_in(["init", "-q"])
    _git_in(["remote", "add", "origin", clone_url])
    try:
        _git_in(["fetch", "--depth", "1", "origin", commit_sha])
    except GitConnectorError:
        # Server disallows arbitrary-SHA fetch: deepen to a full clone.
        _git_in(["fetch", "origin"])
        _git_in(["checkout", "-q", commit_sha])
        return
    _git_in(["checkout", "-q", "FETCH_HEAD"])


def build_provenance(spec: RepoSpec, resolved: ResolvedRef,
                     snapshot_digest: Optional[str] = None) -> dict:
    """The receipt's repository provenance record."""
    return {
        "provider": spec.provider,
        "repository": spec.repository,
        "ref": resolved.requested_ref,
        "commit": resolved.commit_sha,
        "snapshot_digest": snapshot_digest,
    }


def _git(args: list[str], cwd: Optional[Path] = None, timeout: int = 60) -> str:
    """Run git with argv (no shell). Returns stdout. Raises on failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise GitConnectorError("git executable not found on PATH")
    except subprocess.TimeoutExpired:
        raise GitConnectorError(f"git {' '.join(args[:2])} timed out after {timeout}s")
    if proc.returncode != 0:
        # Never echo the clone URL args back when they could contain an
        # embedded credential — trim to the subcommand + tail of stderr.
        tail = (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "unknown error"
        raise GitConnectorError(f"git {args[0]} failed: {tail[:300]}")
    return proc.stdout
