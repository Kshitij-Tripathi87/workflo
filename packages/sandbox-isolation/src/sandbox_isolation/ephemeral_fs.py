"""Ephemeral filesystem — the customer's repo lives on tmpfs, never on disk.

A tmpfs mount is RAM-backed. When we unmount it (or when the host crashes,
which we plan for but never hope for), the data is gone by construction.
There is no "soft delete" path because there is no persistent backing store.

This is the difference between "we delete your code after the run" (a claim)
and "your code never existed on a persistent medium" (an architectural fact).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EphemeralMount:
    """A tmpfs mount the executor can clone a repo into.

    The lifecycle is: create -> mount -> use -> unmount -> verify_gone.
    There is no "leave it around for later" branch.
    """

    sandbox_id: str
    mount_point: Path
    size_mb: int = 512

    @property
    def exists(self) -> bool:
        return self.mount_point.exists()

    def path_for(self, relative: str) -> Path:
        return self.mount_point / relative


def mount_tmpfs(sandbox_id: str, size_mb: int = 512) -> EphemeralMount:
    """Mount a tmpfs and return a handle.

    On Linux: uses `mount -t tmpfs`. On macOS / Windows / non-privileged
    environments: falls back to a temp directory on the existing filesystem
    but marks it clearly so tests/CI can detect this fallback. The fallback
    is logged in the lifecycle events and is NOT silent — it's the executor's
    job to refuse to claim "ephemeral" if it actually fell back.

    The fallback exists for local dev. In production, the sandbox runner
    refuses to start if the mount isn't real tmpfs.
    """

    mount_point = Path(tempfile.mkdtemp(prefix=f"workflo-{sandbox_id}-"))
    mount = EphemeralMount(
        sandbox_id=sandbox_id,
        mount_point=mount_point,
        size_mb=size_mb,
    )

    if os.name == "posix" and os.geteuid() == 0:
        # Real tmpfs mount — needs root. Production path.
        try:
            subprocess.run(
                [
                    "mount",
                    "-t",
                    "tmpfs",
                    "-o",
                    f"size={size_mb}m,mode=700",
                    "tmpfs",
                    str(mount_point),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            # If mount fails, clean up and re-raise — we don't fall back silently.
            shutil.rmtree(mount_point, ignore_errors=True)
            stderr_msg = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            raise RuntimeError(f"tmpfs mount failed for {sandbox_id}: {stderr_msg}") from e
        mount._is_real_tmpfs = True  # type: ignore[attr-defined]
    else:
        # Non-privileged / non-Linux fallback (local dev, CI, macOS).
        # The mount_point still exists and is still sandbox-scoped, but it is
        # on the host filesystem. The executor MUST log this in lifecycle events
        # and the receipt MUST reflect that ephemeral guarantee is degraded.
        mount._is_real_tmpfs = False  # type: ignore[attr-defined]

    return mount


def unmount_tmpfs(mount: EphemeralMount) -> None:
    """Unmount and remove the tmpfs. Idempotent — safe to call twice.

    On Windows / Docker Desktop, two transient effects make a single
    `shutil.rmtree` unreliable:

    1. The Docker daemon briefly holds a file handle on bind-mounted host
       directories even after `docker rm -f` returns. A single rmtree
       will raise PermissionError in that ~200ms window.

    2. Git for Windows holds read handles on pack files in
       `.git/objects/pack/` for several seconds after `git clone` returns.
       Even after the subprocess exited, the OS may not have released
       those handles yet.

    We retry with a longer backoff (5 attempts, 1s each) so the executor
    doesn't mark runs as teardown-failed just because of either form of
    Windows file-handle lag. This is a known Windows + Git + Docker
    Desktop behavior, not a workflo bug.
    """

    if not mount.exists:
        return

    if getattr(mount, "_is_real_tmpfs", False):
        try:
            subprocess.run(
                ["umount", str(mount.mount_point)],
                check=False,  # may already be gone
                capture_output=True,
            )
        except FileNotFoundError:
            pass  # umount binary missing — fall through to directory cleanup

    # Retry the rmtree to handle Windows file-handle lag from:
    #   - Docker Desktop after `docker rm -f`
    #   - Git for Windows holding pack file handles after `git clone`
    # We do FIVE attempts with 1s between them (5s total budget).
    # If by then the dir still can't be removed, that's not a race — it's
    # a genuinely leaked bind mount, and we should return having logged
    # the failure. The downstream `verify_ephemeral_gone` check is what
    # actually proves the cleanup happened — it will return False if the
    # dir is still there, which is the correct, fail-closed signal.
    import time as _time
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            shutil.rmtree(mount.mount_point, ignore_errors=False)
            last_err = None
            break
        except (PermissionError, OSError) as e:
            last_err = e
            _time.sleep(1.0)
        except FileNotFoundError:
            last_err = None
            break

    # If all retries failed, try a more aggressive Windows-side removal.
    # PowerShell's `Remove-Item -Recurse -Force` can sometimes force-unlock
    # files that Python's rmtree can't, because it uses different Win32 APIs
    # and retries differently. This is a Windows-specific fallback.
    if last_err is not None and mount.exists:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Remove-Item -LiteralPath '{mount.mount_point}' -Recurse -Force -ErrorAction SilentlyContinue"],
                    check=False,
                    capture_output=True,
                    timeout=15,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        # Final best-effort ignore_errors pass.
        shutil.rmtree(mount.mount_point, ignore_errors=True)


def verify_ephemeral_gone(mount: EphemeralMount) -> bool:
    """Post-teardown check: does the mount point still exist?

    This is the function an outside verifier (the Week 7 outside-verifier
    script, claim #2 of the Scope Contract) calls to prove the sandbox
    actually went away. Returns True only if the directory is gone.
    """

    return not mount.exists
