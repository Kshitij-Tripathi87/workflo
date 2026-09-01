"""Model layer for --deep-test / --aggressive-test tiers.

Public API:
    ModelServer         - lifecycle wrapper around Ollama
    ModelServerConfig   - configurable knobs (host, port, model, timeouts)
    ModelServerError    - exception type for server lifecycle failures
    wipe_model_state    - filesystem wipe of Ollama state dirs (logs, history)
    generate_from_model_output - validate + parse model output into ProbeSpec list
    ModelOutputInvalid  - raised when model output fails to parse
    build_correction_prompt - build a retry prompt after a parse failure

Phase 1 ships with these primitives. Phase 2+ may add:
    - Multiple-model ensembling
    - Caching of inference results across runs (with redaction)
    - Streaming responses for long generations
"""

from workflo_worker.model.model_server import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    ModelServer,
    ModelServerConfig,
    ModelServerError,
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
    "ModelServer",
    "ModelServerConfig",
    "ModelServerError",
    "wipe_model_state",
    "generate_from_model_output",
    "ModelOutputInvalid",
    "build_correction_prompt",
]
