"""Teardown proof — post-run evidence the sandbox actually went away.

This is what backs Claim #2 of the Scope Contract: "the sandbox is destroyed
after every run, with no residue." The claim is verifiable because these
functions can be called from OUTSIDE the sandbox (by the outside-verifier
script in Week 7) and they return ground truth about what survived.

If you find yourself tempted to soften these checks ("we tried to delete it"
rather than "we verified it's gone"), don't. Soft checks are how privacy
guarantees become lies.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, UTC
from typing import Optional

from workflo_schema.sandbox import TeardownProof


def verify_container_gone(container_id: Optional[str]) -> bool:
    """Confirm the container no longer exists via `docker inspect`.

    Returns True only if Docker explicitly reports the container is gone.
    Returns False on any error (container still running, Docker daemon
    unreachable, container exists, etc.) — fail closed, not open.

    On Docker Desktop for Windows, the daemon briefly reports a just-removed
    container as still existing via `docker inspect` for ~200ms after
    `docker rm -f` returns. We retry a few times so we don't mark a
    successful teardown as failed just because of daemon-side bookkeeping lag.
    """

    if not container_id:
        # No container_id means we never created one — vacuously gone.
        return True

    import time as _time
    # Three attempts with 200ms backoff. If by then the daemon still
    # reports the container as existing, that's not a race — that's a
    # genuinely leaked container, and we should return False (fail closed).
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["docker", "inspect", container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # If we can't inspect, we can't claim it's gone. Fail closed.
            return False

        # docker inspect returns exit code 0 if the container exists,
        # non-zero if it doesn't. Non-zero + any "not found" style error
        # is the success case for us. Different Docker distributions
        # phrase this differently:
        #   - Docker Engine (Linux): "No such container: <id>"
        #   - Docker Desktop (mac/win): "error: no such object: <id>"
        #   - Some errors include "Error response from daemon: No such container"
        # We accept any stderr that looks like "container/image doesn't exist".
        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            gone_phrases = [
                "no such container",
                "no such object",
                "not found",
                "no such image",
            ]
            if any(phrase in stderr_lower for phrase in gone_phrases):
                return True
            # Non-zero exit with an unrelated error message — that's not
            # "container gone", that's "something else went wrong".
            # Treat as container still existing (fail closed).
            return False

        # Exit code 0 means the container still exists. Retry to handle
        # daemon-side bookkeeping lag after `docker rm -f`.
        _time.sleep(0.5)

    # Three attempts all reported the container as existing — this is a
    # genuinely leaked container, not a race. Fail closed.
    return False


def build_teardown_proof(
    sandbox_id: str,
    container_id: Optional[str],
    filesystem_wipe_method: str = "tmpfs_umount",
    no_snapshot_retained: bool = True,
) -> TeardownProof:
    """Build a TeardownProof by performing the actual post-checks.

    This is the function that turns "we tried to clean up" into "we
    verified it's clean." The proof is the artifact — without calling
    verify_container_gone, you don't have a proof, you have a wish.
    """

    container_removed = verify_container_gone(container_id)
    # The filesystem check happens via verify_ephemeral_gone() in the
    # executor, because we need the EphemeralMount handle to check its
    # mount_point. This function takes the boolean as input.

    return TeardownProof(
        sandbox_id=sandbox_id,
        container_id=container_id,
        filesystem_wipe_method=filesystem_wipe_method,
        container_removed=container_removed,
        filesystem_removed=False,  # set by executor after ephemeral_fs check
        no_snapshot_retained=no_snapshot_retained,
        destroyed_at=datetime.now(UTC),
    )
