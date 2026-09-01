"""workflo sandbox executor — the per-job ephemeral lifecycle wrapper.

This is the thing that ties together:
  - mount_tmpfs:               the customer's repo is cloned onto a RAM-backed fs
  - Docker container:          network_mode=none, no volumes, read-only root
  - worker-engine payload:     pytest + the generalized test engine
  - teardown:                  container killed + tmpfs unmounted + verified gone
  - receipt signing:           Ed25519 signature over the canonical receipt

The exit gate for Phase 1 is: `workflo run <repo-url>` works end-to-end
on an unfamiliar repo, container + tmpfs are provably gone afterward, and
the receipt verifies.
"""

from workflo_executor.executor import SandboxExecutor, SandboxRunResult, generate_sandbox_id
from workflo_executor.runtime import ContainerRuntime, DockerContainerRuntime

__all__ = [
    "SandboxExecutor",
    "SandboxRunResult",
    "generate_sandbox_id",
    "ContainerRuntime",
    "DockerContainerRuntime",
]

__version__ = "0.1.0"
