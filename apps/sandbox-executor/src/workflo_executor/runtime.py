"""ContainerRuntime abstraction — a protocol-based interface for container backends.

The executor talks to a ContainerRuntime, not directly to docker_runner.
This lets us swap backends (Docker CLI, Fargate, gVisor, podman) without
touching the executor's orchestration logic.

Phase 1 ships with DockerContainerRuntime (wraps docker_runner.py).
Phase 2+ can add FargateContainerRuntime, etc.

Usage:
    runtime = DockerContainerRuntime()
    container_id = runtime.create(config)
    runtime.start(container_id)
    result = runtime.wait(container_id, timeout=60)
    runtime.kill(container_id)
    exists = runtime.exists(container_id)
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from workflo_executor.docker_runner import (
    ContainerConfig,
    ContainerResult,
    container_exists,
    create_container,
    kill_container,
    start_container,
    wait_container,
)


@runtime_checkable
class ContainerRuntime(Protocol):
    """Protocol that any container backend must implement.

    The executor depends on this interface, not on docker_runner directly.
    This is the seam where Fargate / gVisor / podman backends plug in.

    Contract:
        - create() returns a container_id string, raises on failure
        - start() is fire-and-forget, raises on failure
        - wait() blocks until exit or timeout, returns ContainerResult
        - kill() is idempotent (safe to call on already-removed containers)
        - exists() returns False for None container_id or missing container
    """

    def create(self, config: ContainerConfig) -> str:
        """Create a container (stopped) and return its ID."""
        ...

    def start(self, container_id: str, timeout_seconds: int = 30) -> None:
        """Start a previously-created container."""
        ...

    def wait(
        self, container_id: str, timeout_seconds: int = 600
    ) -> ContainerResult:
        """Block until the container exits or timeout fires."""
        ...

    def kill(self, container_id: str) -> None:
        """Kill and remove a container. Idempotent — safe after teardown."""
        ...

    def exists(self, container_id: Optional[str]) -> bool:
        """Return True if the container still exists on the backend."""
        ...


class DockerContainerRuntime:
    """Concrete ContainerRuntime backed by the Docker CLI (via docker_runner).

    This is the default runtime for Phase 1. It delegates every call to
    docker_runner.py functions, which use subprocess.run with list form
    (no shell=True) and validate all inputs.
    """

    def create(self, config: ContainerConfig) -> str:
        return create_container(config)

    def start(self, container_id: str, timeout_seconds: int = 30) -> None:
        start_container(container_id, timeout_seconds=timeout_seconds)

    def wait(
        self, container_id: str, timeout_seconds: int = 600
    ) -> ContainerResult:
        return wait_container(container_id, timeout_seconds=timeout_seconds)

    def kill(self, container_id: str) -> None:
        kill_container(container_id)

    def exists(self, container_id: Optional[str]) -> bool:
        return container_exists(container_id)


__all__ = [
    "ContainerRuntime",
    "DockerContainerRuntime",
    "ContainerConfig",
    "ContainerResult",
]
