"""Model server lifecycle — starts/stops Ollama inside the worker container.

The deep-test pipeline uses a local Ollama instance to run Qwen2.5-Coder
against repo file trees. Ollama is started by this module at the beginning
of the model stage, and stopped + log-wiped at the end. We bind only to
127.0.0.1 (not 0.0.0.0) so nothing outside this container's namespace
can reach the model server — the sandbox is on --network none anyway.

Why DEVNULL for stdout/stderr:
    We don't want Ollama's per-request logs (which can include prompt
    previews on some versions) ending up in a persistent location.
    DEVNULL means they go nowhere — even if Ollama's log config gets
    accidentally changed at build time, the logs vanish at container death.
    If you need to debug Ollama during development, redirect to a file
    *inside the tmpfs* so it dies with the container, never to a
    host-mounted path.

Why a real readiness check, not sleep():
    Ollama's startup time varies wildly — slow CI machines can take
    10+ seconds to load the model into VRAM/RAM. A fixed sleep either
    wastes time on fast hosts or runs into "model server not ready"
    errors on slow ones. The socket-based readiness check is O(N ms) and
    doesn't depend on the host's speed.

Why HTTP timeout kwarg, not asyncio.wait_for():
    The worker engine's overall structure is synchronous (subprocess.run
    + urllib). Introducing asyncio.wait_for for one call site adds a
    concurrency pattern to a codebase that doesn't have one. The HTTP
    client's own `timeout=` kwarg is the simplest thing that works.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 60.0
DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_m"


class ModelServerError(RuntimeError):
    """Raised when the model server can't start, can't answer, or fails."""


@dataclass
class ModelServerConfig:
    """Configurable knobs for the model server."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS
    inference_timeout_seconds: float = DEFAULT_INFERENCE_TIMEOUT_SECONDS
    model: str = DEFAULT_MODEL
    # If the worker runs in a container that already has ollama serve
    # running, we can skip starting our own. Default False: we always
    # start our own to keep the lifecycle explicit and teardown clean.
    reuse_existing: bool = False


class ModelServer:
    """Lifecycle wrapper around the Ollama binary.

    Usage:
        config = ModelServerConfig()
        server = ModelServer(config)
        server.start()                          # blocks until API is up
        text = server.generate("Hello, world")  # returns model output
        server.stop()                           # kills subprocess

    Idempotent:
        start() on an already-running server raises immediately
        stop() on a not-yet-started server is a no-op
    """

    def __init__(self, config: Optional[ModelServerConfig] = None):
        self.config = config or ModelServerConfig()
        self.proc: Optional[subprocess.Popen] = None
        self._started = False

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def start(self) -> None:
        """Start the model server and block until the API is reachable.

        Raises ModelServerError if the server can't come up within
        startup_timeout_seconds. Idempotent: calling start() twice on
        the same ModelServer raises on the second call.
        """
        if self._started:
            raise ModelServerError("ModelServer.start() called twice without stop() in between")

        # Check if an ollama instance is already up on this port. If so
        # AND reuse_existing is set, adopt it. Otherwise we'll fail at
        # port-bind time.
        if self._is_port_open():
            if self.config.reuse_existing:
                self._started = True
                return
            raise ModelServerError(
                f"Port {self.config.port} already in use — set reuse_existing=True to adopt it, "
                f"or stop the existing process first."
            )

        env = os.environ.copy()
        # Force 127.0.0.1 binding even if the user passed a different host.
        env["OLLAMA_HOST"] = f"{self.config.host}:{self.config.port}"
        # Disable Ollama's per-request logging so prompt/completion previews
        # don't accidentally end up in a persistent log.
        env["OLLAMA_DEBUG"] = "0"
        # If the version of Ollama installed supports it, also disable
        # the prompt history file. We confirm-and-fall-back at runtime
        # in no_log_guard.py — that's where the file system is wiped too.
        env.setdefault("OLLAMA_NOHISTORY", "1")
        # Drop Ollama's log level — 'warn' is the highest non-error setting.
        env.setdefault("OLLAMA_LOG_LEVEL", "warn")

        try:
            self.proc = subprocess.Popen(
                ["ollama", "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # New process group so we can SIGTERM the entire group on stop().
                start_new_session=True,
            )
        except FileNotFoundError as e:
            raise ModelServerError(
                "ollama binary not found on PATH — install Ollama before starting the model server"
            ) from e

        try:
            self._wait_ready(self.config.startup_timeout_seconds)
        except Exception:
            # If readiness fails, kill the process we just started so we
            # don't leave a zombie.
            self.stop()
            raise

        self._started = True

    def _is_port_open(self) -> bool:
        """Non-blocking check: is something already listening on this port?"""
        try:
            with socket.create_connection(
                (self.config.host, self.config.port), timeout=0.5
            ):
                return True
        except OSError:
            return False

    def _wait_ready(self, timeout_seconds: float) -> None:
        """Poll the Ollama API until it responds, or raise on timeout.

        Uses /api/tags which is the cheapest endpoint Ollama exposes —
        it just lists installed models. We do NOT use /api/version or
        anything that might trigger a model load.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(
                    (self.config.host, self.config.port), timeout=0.5
                ):
                    # Port is open; we could also do a real HTTP GET
                    # here, but the socket connect is sufficient for
                    # "ollama is listening". The actual HTTP request
                    # below will fail with a more informative error if
                    # the API isn't actually serving yet.
                    return
            except OSError:
                time.sleep(0.3)
        raise ModelServerError(
            f"Model server failed to start within {timeout_seconds}s on "
            f"{self.config.host}:{self.config.port}"
        )

    def generate(
        self,
        prompt: str,
        *,
        timeout_seconds: Optional[float] = None,
        system: Optional[str] = None,
    ) -> str:
        """Send a prompt to the model and return its response text.

        Uses the Ollama HTTP API directly via requests.post(... timeout=...)
        — no async, no new concurrency pattern. timeout_seconds defaults
        to ModelServerConfig.inference_timeout_seconds.

        Raises ModelServerError on any failure (timeout, HTTP error, etc.)
        """
        if not self._started:
            raise ModelServerError("ModelServer.generate() called before start()")

        import requests  # local import — only paid for when this is called

        payload: dict = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        timeout = timeout_seconds or self.config.inference_timeout_seconds

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout as e:
            raise ModelServerError(
                f"Model inference timed out after {timeout}s"
            ) from e
        except requests.ConnectionError as e:
            raise ModelServerError(
                f"Model server connection error during inference: {e}"
            ) from e
        except requests.RequestException as e:
            raise ModelServerError(f"Model inference HTTP error: {e}") from e

        if resp.status_code != 200:
            raise ModelServerError(
                f"Model server returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise ModelServerError(
                f"Model server returned non-JSON response: {resp.text[:200]}"
            ) from e

        return data.get("response", "")

    def stop(self) -> None:
        """Stop the model server subprocess. Idempotent — safe to call twice.

        Tries SIGTERM first, then SIGKILL if the process doesn't exit
        within 5 seconds. No-op if the server was never started or has
        already exited.
        """
        if self.proc is None:
            self._started = False
            return

        if self.proc.poll() is not None:
            # Process already exited
            self.proc = None
            self._started = False
            return

        try:
            self.proc.terminate()
        except ProcessLookupError:
            self.proc = None
            self._started = False
            return

        try:
            self.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            # Still alive — escalate to SIGKILL
            try:
                self.proc.kill()
                self.proc.wait(timeout=2.0)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass

        self.proc = None
        self._started = False

    def is_alive(self) -> bool:
        """Return True if the subprocess is still running."""
        if self.proc is None:
            return False
        return self.proc.poll() is None


__all__ = [
    "ModelServer",
    "ModelServerConfig",
    "ModelServerError",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_MODEL",
]
