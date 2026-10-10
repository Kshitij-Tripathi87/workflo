"""Fail-closed llama.cpp routing and validation for Workflo."""

from workflo_ai_integration.model_router import (
    ADAPTER_REGISTRY,
    FLAG_TASK_MAP,
    AdapterLoadError,
    GenerationValidationError,
    ModelRouter,
    RouterConfig,
)
from workflo_ai_integration.schemas import (
    ProposeInvariantCall,
    ReportNarrative,
    WriteTestCall,
)

__all__ = [
    "ADAPTER_REGISTRY",
    "FLAG_TASK_MAP",
    "AdapterLoadError",
    "GenerationValidationError",
    "ModelRouter",
    "ProposeInvariantCall",
    "ReportNarrative",
    "RouterConfig",
    "WriteTestCall",
]
