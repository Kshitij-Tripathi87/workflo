"""Tenant Shield shared schema package.

Exposes the canonical Pydantic models used by every service in the platform:
  - RunSpec:      submitted by the CLI, consumed by the Worker
  - TestResult:   produced by the Worker, stored by the Backend
  - RunSummary:   aggregated result metadata
  - Organization/Project/ApiKey: auth and org models
"""

from workflo_schema.enums import Goal, RunStatus, PlanTier, ApiKeyScope, ArtifactType, BrowserMode
from workflo_schema.run_spec import (
    RunSpec,
    RunConfig,
    TestTargets,
    ArtifactsConfig,
)
from workflo_schema.results import TestResult, RunSummary, Finding
from workflo_schema.auth import Organization, Project, ApiKey
from workflo_schema.sandbox import (
    SandboxSpec,
    SandboxLifecycleEvent,
    TeardownProof,
    CanaryCheckResult,
    RunReport,
    SignedReceipt,
    AgentActivity,
    LocalModelProvenance,
)
from workflo_schema.inference import (
    ALLOWED_AGENT_TOOLS,
    INFERENCE_PROTOCOL_VERSION,
    InferenceBudget,
    InferenceGatewayRequest,
    InferenceGatewayResponse,
    InferencePlan,
    InferenceProvenance,
    PlanStep,
    RuntimeObservation,
    SourcePayloadError,
    sanitize_observations,
)

__all__ = [
    "Goal",
    "RunStatus",
    "PlanTier",
    "ApiKeyScope",
    "ArtifactType",
    "BrowserMode",
    "RunSpec",
    "RunConfig",
    "TestTargets",
    "ArtifactsConfig",
    "TestResult",
    "RunSummary",
    "Finding",
    "Organization",
    "Project",
    "ApiKey",
    "SandboxSpec",
    "SandboxLifecycleEvent",
    "TeardownProof",
    "CanaryCheckResult",
    "RunReport",
    "SignedReceipt",
    "AgentActivity",
    "LocalModelProvenance",
    "ALLOWED_AGENT_TOOLS",
    "INFERENCE_PROTOCOL_VERSION",
    "InferenceBudget",
    "InferenceGatewayRequest",
    "InferenceGatewayResponse",
    "InferencePlan",
    "InferenceProvenance",
    "PlanStep",
    "RuntimeObservation",
    "SourcePayloadError",
    "sanitize_observations",
]

__version__ = "1.1.1"
