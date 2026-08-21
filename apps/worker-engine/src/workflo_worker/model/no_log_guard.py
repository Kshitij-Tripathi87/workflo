"""no_log_guard — wipe Ollama state at teardown.

The model server (Ollama) writes state to several on-disk locations:
    ~/.ollama/logs/    — per-request logs (can contain prompt previews
                          on some Ollama versions)
    ~/.ollama/history   — interactive REPL history (not used in this
                          pipeline, but a default Ollama location)
    ~/.ollama/.tmp      — temporary files during inference

If those files survive teardown, a receipt claiming "model inference
teardown succeeded" would be a lie — the customer's prompt may still
sit on disk. This module is the cleanup.

Design contract:
    wipe_model_state() is called in the SAME teardown path as the
    container kill and tmpfs unmount — treat it as part of teardown,
    not a separate optional cleanup step.

    Failure modes:
    - rmtree raises PermissionError       -> let it raise. Don't swallow.
    - rmtree raises FileNotFoundError     -> that's fine, the dir was already gone.
    - Path exists after our cleanup       -> return False so the receipt can
                                              record "teardown failed" for this
                                              step (fail closed).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional


# Default Ollama state directories to wipe. These paths are relative to
# $HOME unless absolute. We resolve via Path.expanduser() at runtime.
DEFAULT_STATE_DIRS = [
    ".ollama/logs",
    ".ollama/history",
    ".ollama/.tmp",
]


def resolve_state_dirs(extra_dirs: Optional[list[str]] = None) -> list[Path]:
    """Return absolute Paths for the Ollama state directories.

    `extra_dirs` may include additional absolute paths to wipe (e.g.
    OLLAMA_MODELS path, if we want to wipe the cached models too —
    usually we DON'T, but it's configurable).

    All paths are resolved against $HOME (or the user-supplied override).
    """
    home = Path(os.path.expanduser("~"))
    paths = [home / Path(p) for p in DEFAULT_STATE_DIRS]
    if extra_dirs:
        paths.extend(Path(p) for p in extra_dirs)
    return paths


def wipe_model_state(
    extra_dirs: Optional[list[str]] = None,
    *,
    max_retries: int = 5,
    retry_sleep_seconds: float = 0.5,
) -> bool:
    """Wipe Ollama state directories and verify they're gone.

    Returns True only if every target directory was either already
    absent or was successfully removed. Returns False if any directory
    still exists after the wipe — the receipt should record
    `model_inference_teardown: false` (fail closed).

    Retries on PermissionError because Windows + Docker Desktop +
    Ollama has the same kind of file-handle lag as Git pack files: the
    subprocess may have exited but the OS hasn't released the handle yet.

    Raises:
        OSError: On a non-retriable filesystem error (NOT PermissionError —
                 that one is retried). Letting this propagate is the
                 "don't swallow errors" stance from the plan: a receipt
                 that lies about teardown is the worst possible outcome.
    """
    paths = resolve_state_dirs(extra_dirs=extra_dirs)

    # Track which paths still need wiping after our retries.
    remaining = [p for p in paths if p.exists()]

    for attempt in range(max_retries):
        if not remaining:
            return True

        still_here = []
        for path in remaining:
            try:
                shutil.rmtree(path, ignore_errors=False)
            except FileNotFoundError:
                # Already gone — that's the success case
                continue
            except PermissionError as e:
                # Windows file-handle lag. Retry.
                still_here.append(path)
            except OSError:
                # Other OS error (e.g. cross-device link). Let it propagate
                # — that's the "don't swallow errors" stance.
                raise

        remaining = still_here
        if remaining:
            time.sleep(retry_sleep_seconds)

    # After all retries, anything still in `remaining` is genuinely there.
    # That's a real leak, not a race.
    if remaining:
        return False

    return True


def confirm_no_ollama_state(extra_dirs: Optional[list[str]] = None) -> bool:
    """Pure check: do any Ollama state files exist?

    Used both before wipe_model_state() (to confirm there's something to
    wipe) and after (to confirm the wipe succeeded — though
    wipe_model_state() does its own verification).

    This function is the "do not trust the receipt without a filesystem
    check" principle applied to the model inference stage.
    """
    paths = resolve_state_dirs(extra_dirs=extra_dirs)
    return not any(p.exists() for p in paths)


__all__ = [
    "DEFAULT_STATE_DIRS",
    "resolve_state_dirs",
    "wipe_model_state",
    "confirm_no_ollama_state",
]
