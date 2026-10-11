"""Model layer for deep/aggressive tiers.

``LlamaCppRuntime`` is the release backend: it verifies pinned GGUF artifacts,
owns a loopback llama-server process, and proves teardown. ``ModelServer`` and
the Ollama parser exports remain temporarily available only for compatibility
with pre-release images and tests; production selection defaults to llama.cpp.
"""

from workflo_worker.model.model_server import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    ModelServer,
    ModelServerConfig,
    ModelServerError,
)
from workflo_worker.model.llamacpp_runtime import (
    ADAPTER_NAMES,
    GGUFArtifact,
    LlamaCppRuntime,
    LlamaCppRuntimeConfig,
    LlamaCppRuntimeError,
)
from workflo_worker.model.no_log_guard import wipe_model_state
from workflo_worker.model.probe_adapter import (
    ModelOutputInvalid,
    build_correction_prompt,
    generate_from_model_output,
)


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_MODEL",
    "DEFAULT_PORT",
    "ADAPTER_NAMES",
    "GGUFArtifact",
    "LlamaCppRuntime",
    "LlamaCppRuntimeConfig",
    "LlamaCppRuntimeError",
    "ModelServer",
    "ModelServerConfig",
    "ModelServerError",
    "wipe_model_state",
    "generate_from_model_output",
    "ModelOutputInvalid",
    "build_correction_prompt",
]
