"""Owned llama.cpp lifecycle with immutable GGUF verification.

The worker starts ``llama-server`` inside its own network namespace and binds it
to loopback. Repository source may be sent to this local process, but never to
a non-loopback endpoint. Every model and adapter is SHA-256 verified before the
process starts, and no slot-cache persistence flag is permitted.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import httpx

ADAPTER_NAMES = ("test-gen", "reasoning", "reporting")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PINNED_IMAGE_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


class LlamaCppRuntimeError(RuntimeError):
    """Raised when artifact validation, startup, health, or teardown fails."""


@dataclass(frozen=True)
class GGUFArtifact:
    name: str
    path: Path
    sha256: str

    def verify(self) -> None:
        expected = self.sha256
        if not _SHA256_RE.fullmatch(expected):
            raise LlamaCppRuntimeError(f"{self.name} has invalid SHA-256 value")
        try:
            resolved = self.path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise LlamaCppRuntimeError(f"{self.name} is missing: {self.path}") from exc
        if not resolved.is_file():
            raise LlamaCppRuntimeError(f"{self.name} is not a regular file: {resolved}")

        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        if actual != expected:
            raise LlamaCppRuntimeError(
                f"{self.name} SHA-256 mismatch: expected {expected}, got {actual}"
            )


@dataclass(frozen=True)
class LlamaCppRuntimeConfig:
    executable: str
    model_id: str
    image: str
    base_model: GGUFArtifact
    adapters: Mapping[str, GGUFArtifact]
    host: str = "127.0.0.1"
    port: int = 8080
    context_size: int = 8192
    startup_timeout_seconds: float = 120.0
    request_timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "LlamaCppRuntimeConfig":
        def required(name: str) -> str:
            value = (os.environ.get(name) or "").strip()
            if not value:
                raise LlamaCppRuntimeError(f"required environment variable is missing: {name}")
            return value

        def artifact(label: str, path_var: str, hash_var: str) -> GGUFArtifact:
            return GGUFArtifact(label, Path(required(path_var)), required(hash_var))

        adapters = {
            "test-gen": artifact(
                "test-gen adapter",
                "WORKFLO_LLAMACPP_TEST_GEN_GGUF",
                "WORKFLO_LLAMACPP_TEST_GEN_SHA256",
            ),
            "reasoning": artifact(
                "reasoning adapter",
                "WORKFLO_LLAMACPP_REASONING_GGUF",
                "WORKFLO_LLAMACPP_REASONING_SHA256",
            ),
            "reporting": artifact(
                "reporting adapter",
                "WORKFLO_LLAMACPP_REPORTING_GGUF",
                "WORKFLO_LLAMACPP_REPORTING_SHA256",
            ),
        }
        try:
            port = int(os.environ.get("WORKFLO_LLAMACPP_PORT", "8080"))
            context_size = int(os.environ.get("WORKFLO_LLAMACPP_CONTEXT", "8192"))
            startup_timeout = float(os.environ.get("WORKFLO_LLAMACPP_STARTUP_TIMEOUT", "120"))
            request_timeout = float(os.environ.get("WORKFLO_LLAMACPP_REQUEST_TIMEOUT", "120"))
        except ValueError as exc:
            raise LlamaCppRuntimeError("invalid numeric llama.cpp configuration") from exc

        return cls(
            executable=(os.environ.get("WORKFLO_LLAMACPP_BINARY") or "llama-server").strip(),
            model_id=required("WORKFLO_LLAMACPP_MODEL_ID"),
            image=required("WORKFLO_LLAMACPP_IMAGE"),
            base_model=artifact(
                "base model",
                "WORKFLO_LLAMACPP_BASE_GGUF",
                "WORKFLO_LLAMACPP_BASE_SHA256",
            ),
            adapters=adapters,
            host=(os.environ.get("WORKFLO_LLAMACPP_HOST") or "127.0.0.1").strip(),
            port=port,
            context_size=context_size,
            startup_timeout_seconds=startup_timeout,
            request_timeout_seconds=request_timeout,
        )

    def validate(self) -> None:
        if self.host != "localhost":
            try:
                if not ipaddress.ip_address(self.host).is_loopback:
                    raise ValueError
            except ValueError as exc:
                raise LlamaCppRuntimeError(
                    "source-bearing llama.cpp endpoint must bind to loopback"
                ) from exc
        if not (1 <= self.port <= 65535):
            raise LlamaCppRuntimeError("llama.cpp port must be between 1 and 65535")
        if self.context_size < 1024:
            raise LlamaCppRuntimeError("llama.cpp context size must be at least 1024")
        if self.startup_timeout_seconds <= 0 or self.request_timeout_seconds <= 0:
            raise LlamaCppRuntimeError("llama.cpp timeouts must be positive")
        if not self.model_id or len(self.model_id) > 128:
            raise LlamaCppRuntimeError("llama.cpp model id is missing or too long")
        if not _PINNED_IMAGE_RE.fullmatch(self.image):
            raise LlamaCppRuntimeError(
                "WORKFLO_LLAMACPP_IMAGE must be pinned as image@sha256:<64 hex>"
            )
        if set(self.adapters) != set(ADAPTER_NAMES):
            raise LlamaCppRuntimeError(
                f"exactly these adapters are required: {', '.join(ADAPTER_NAMES)}"
            )
        self.base_model.verify()
        for name in ADAPTER_NAMES:
            self.adapters[name].verify()
        resolved_paths = {
            self.base_model.path.resolve(),
            *(self.adapters[name].path.resolve() for name in ADAPTER_NAMES),
        }
        if len(resolved_paths) != 1 + len(ADAPTER_NAMES):
            raise LlamaCppRuntimeError("base model and adapters must be four distinct files")


@dataclass
class LlamaCppRuntime:
    config: LlamaCppRuntimeConfig
    process: subprocess.Popen | None = field(default=None, init=False)
    _scratch: Path | None = field(default=None, init=False)
    _started: bool = field(default=False, init=False)

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def command(self) -> list[str]:
        command = [
            self.config.executable,
            "-m",
            str(self.config.base_model.path),
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "-c",
            str(self.config.context_size),
        ]
        for name in ADAPTER_NAMES:
            command += ["--lora", str(self.config.adapters[name].path)]
        command.append("--lora-init-without-apply")
        # Deliberately no --slot-save-path: prompts/source must never persist.
        return command

    def start(self) -> None:
        if self._started or self.process is not None:
            raise LlamaCppRuntimeError("llama.cpp runtime start called twice")
        self.config.validate()
        if self._port_open():
            raise LlamaCppRuntimeError(
                f"llama.cpp loopback port is already in use: {self.config.port}"
            )

        executable = self.config.executable
        if os.path.sep not in executable and shutil.which(executable) is None:
            raise LlamaCppRuntimeError(f"llama-server executable not found: {executable}")

        self._scratch = Path(tempfile.mkdtemp(prefix="workflo-llamacpp-"))
        env = os.environ.copy()
        for name in ("home", "cache", "tmp"):
            (self._scratch / name).mkdir(mode=0o700)
        env.update(
            {
                "HOME": str(self._scratch / "home"),
                "XDG_CACHE_HOME": str(self._scratch / "cache"),
                "TMPDIR": str(self._scratch / "tmp"),
            }
        )

        try:
            self.process = subprocess.Popen(
                self.command,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._wait_ready()
            self._started = True
        except FileNotFoundError as exc:
            self.stop()
            raise LlamaCppRuntimeError(f"llama-server executable not found: {executable}") from exc
        except Exception:
            self.stop()
            raise

    def _port_open(self) -> bool:
        try:
            with socket.create_connection((self.config.host, self.config.port), timeout=0.25):
                return True
        except OSError:
            return False

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        last_error = "not ready"
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise LlamaCppRuntimeError(
                    f"llama-server exited during startup with code {self.process.returncode}"
                )
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(0.25)
        raise LlamaCppRuntimeError(
            f"llama-server was not healthy after {self.config.startup_timeout_seconds}s: "
            f"{last_error}"
        )

    def stop(self) -> bool:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
        alive = process is not None and process.poll() is None
        self.process = None
        self._started = False

        scratch = self._scratch
        self._scratch = None
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=False)
        return not alive and (scratch is None or not scratch.exists())

    def provenance(self) -> dict:
        return {
            "backend": "llamacpp",
            "model": self.config.model_id,
            "server_image": self.config.image,
            "base_model_sha256": self.config.base_model.sha256,
            "adapter_sha256": {
                name: self.config.adapters[name].sha256 for name in ADAPTER_NAMES
            },
            "endpoint_scope": "loopback",
            "source_code_included": True,
        }
