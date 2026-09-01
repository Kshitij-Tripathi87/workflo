"""App-under-test startup + port-wait — the `web` tier's bootstrap.

The `web` tier needs the customer's app to be RUNNING inside the sandbox
before Playwright can probe it. This module starts it (shell-free,
token-split invocation per the frozen contract) and blocks until the
requested port opens.

Three distinct failure modes are kept separate so the receipt can tell
them apart:

  - app exited early      -> RuntimeError("app process exited early ...")
  - app never bound       -> TimeoutError("app did not bind to port ...")
  - app bound but crashed -> RuntimeError (from the caller's poll loop)

The caller distinguishes "the app itself crashed" (RuntimeError) from
"the port never opened" (TimeoutError) — a misleading "port never opened"
message for a crashing app is exactly the DX failure this module exists
to avoid.
"""

from __future__ import annotations

import socket
import subprocess
import time
from typing import Optional


def start_app_under_test(
    repo_path: str,
    start_command: str,
    port: int,
    timeout: int = 15,
    stdout: Optional[object] = None,
    stderr: Optional[object] = None,
) -> subprocess.Popen:
    """Start the app under test and wait for it to bind `port`.

    Args:
        repo_path: directory the command runs in (the cloned repo root).
        start_command: shell-free command string (split into tokens; never
            passed through a shell — same discipline as the executor's
            container args).
        port: local port the app is expected to bind.
        timeout: max seconds to wait for the port to open.
        stdout/stderr: overridable for tests (default DEVNULL hides the
            app's own logs from the worker's output stream).

    Returns:
        The Popen handle. The caller MUST terminate it in a finally block.

    Raises:
        RuntimeError: the app process exited before binding the port.
        TimeoutError: the app stayed alive but never bound the port.
    """
    # Token-split invocation, NOT shell=True. The command string comes from
    # the run spec / workflo.yaml and must never reach a shell.
    tokens = start_command.split()
    if not tokens:
        raise RuntimeError("start_command is empty — nothing to launch")

    proc = subprocess.Popen(
        tokens,
        cwd=str(repo_path),
        stdout=stdout if stdout is not None else subprocess.DEVNULL,
        stderr=stderr if stderr is not None else subprocess.DEVNULL,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        # Early-exit check FIRST: a crashing app (bad dependency, syntax
        # error) must fail immediately with "the app crashed", not spin
        # for the full timeout and report a misleading "port never opened".
        if proc.poll() is not None:
            raise RuntimeError(
                f"app process exited early with code {proc.returncode} "
                f"(command: {start_command!r})"
            )
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc
        except OSError:
            # Not bound yet — keep polling until the deadline.
            time.sleep(0.3)

    proc.terminate()
    raise TimeoutError(
        f"app did not bind to port {port} within {timeout}s "
        f"(command: {start_command!r})"
    )


def stop_app_under_test(proc: Optional[subprocess.Popen]) -> None:
    """Best-effort stop of the app under test. Never raises."""
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
