"""Shared contract for privacy-preserving hosted inference.

The hosted model must never receive a repository snapshot or an arbitrary
prompt supplied by a caller.  This module defines the deliberately small
wire contract used by the planner and the control-plane gateway:

    bounded runtime observations -> gateway -> validated tool plan

The gateway builds the system and user prompts itself.  Extra fields are
forbidden at every contract boundary, source-bearing keys are rejected, and
secret-looking values are redacted before a request is forwarded upstream.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Mapping, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


INFERENCE_PROTOCOL_VERSION = 1
MAX_OBSERVATIONS = 60
MAX_OBSERVATION_TEXT = 512
MAX_PLAN_STEPS = 12
MAX_PLAN_REASON = 256
MAX_STEP_ARGS_BYTES = 4096
MAX_PROMPT_BYTES = 64 * 1024

ALLOWED_AGENT_TOOLS = frozenset(
    {"http_get", "http_post", "read_log", "list_files", "read_file"}
)

# These keys are intentionally not part of the observation protocol.  The
# recursive check is defense in depth for hand-written JSON clients and for
# future schema changes.
SOURCE_KEYS = frozenset(
    {
        "source",
        "source_code",
        "sourcecode",
        "repository",
        "repo",
        "repo_path",
        "repository_path",
        "file_content",
        "source_content",
        "raw_prompt",
        "system_prompt",
        "messages",
    }
)

_SECRET_PATTERNS = (
    # Authorization and bearer material
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(basic\s+)[A-Za-z0-9+/=]+"),
    # Assignment-style secrets in logs or error text
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?key|secret|password|token|authorization)"
        r"(\s*[:=]\s*)[^\s,;]+"
    ),
    # PEM private keys
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)

_SOURCE_TEXT_PATTERNS = (
    re.compile(r"(?m)^\s*(def|class|import|from|function|const|let|package|using)\s+\w+"),
    re.compile(r"```(?:python|javascript|typescript|go|rust|java|ruby|sql)?\s*", re.IGNORECASE),
)


class SourcePayloadError(ValueError):
    """Raised when a payload attempts to cross the source-code boundary."""


def canonical_json(value: Any) -> bytes:
    """Serialize protocol data deterministically for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def sha256_json(value: Any) -> str:
    """SHA-256 of canonical JSON protocol data."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def redact_secrets(text: str) -> str:
    """Redact common secret forms without changing ordinary observations."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}<redacted>{match.group(2)}"
                if match.lastindex and match.lastindex >= 2
                else "<redacted>"
            ),
            redacted,
        )
    return redacted


def _contains_source_key(value: Any) -> Optional[str]:
    """Find a prohibited key anywhere in a JSON-like value."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in SOURCE_KEYS:
                return str(key)
            found = _contains_source_key(child)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _contains_source_key(child)
            if found:
                return found
    return None


def _check_observation_text(text: str, field_name: str) -> str:
    """Redact secrets and reject source-like text in an observation field."""
    if len(text) > MAX_OBSERVATION_TEXT:
        raise ValueError(f"{field_name} exceeds {MAX_OBSERVATION_TEXT} characters")
    for pattern in _SOURCE_TEXT_PATTERNS:
        if pattern.search(text):
            raise SourcePayloadError(
                f"source-bearing text is not allowed in observation field {field_name}"
            )
    return redact_secrets(text)


class RuntimeObservation(BaseModel):
    """The only observation shape accepted by the hosted gateway."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(default="", max_length=MAX_OBSERVATION_TEXT)
    tool: str = Field(max_length=64)
    ok: bool
    denied: bool = False
    detail: str = Field(default="", max_length=MAX_OBSERVATION_TEXT)

    @field_validator("tool")
    @classmethod
    def _tool_name(cls, value: str) -> str:
        if value not in ALLOWED_AGENT_TOOLS:
            raise ValueError(f"unknown governed observation tool: {value}")
        return value

    @field_validator("description", "detail")
    @classmethod
    def _sanitize_text(cls, value: str, info):
        return _check_observation_text(value, info.field_name)


class InferenceBudget(BaseModel):
    """Remaining planner budget sent to the gateway."""

    model_config = ConfigDict(extra="forbid")

    batches_left: int = Field(ge=0, le=32)
    tool_calls_left: int = Field(ge=0, le=1000)


MAX_MISSION_CHARS = 512


class InferenceGatewayRequest(BaseModel):
    """Observation-only request accepted by the control-plane gateway."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=INFERENCE_PROTOCOL_VERSION, ge=1, le=1)
    session_id: str = Field(min_length=1, max_length=128)
    app_url: str = Field(min_length=1, max_length=512)
    task: Literal["autonomous_qa"] = "autonomous_qa"
    # The user's natural-language testing mission ("Test authentication and
    # checkout"). User-authored intent, bounded and secret-redacted — the
    # gateway folds it into the server-side prompt. Still no source code:
    # the model learns WHAT to test, never the code under test.
    mission: Optional[str] = Field(default=None, max_length=MAX_MISSION_CHARS)
    budget: InferenceBudget
    observations: list[RuntimeObservation] = Field(default_factory=list, max_length=MAX_OBSERVATIONS)

    @field_validator("mission")
    @classmethod
    def _mission_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return redact_secrets(value[:MAX_MISSION_CHARS])

    @field_validator("app_url")
    @classmethod
    def _internal_app_url(cls, value: str) -> str:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if parsed.scheme != "http" or not (
            host == "workflo.internal" or host.endswith(".workflo.internal")
        ):
            raise ValueError("app_url must be an internal http://*.workflo.internal URL")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_source_keys(cls, value):
        if isinstance(value, Mapping):
            found = _contains_source_key(value)
            if found:
                raise SourcePayloadError(
                    f"source-bearing field {found!r} is not accepted by the inference gateway"
                )
        return value


class PlanStep(BaseModel):
    """One tool request returned by the hosted model."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=MAX_PLAN_REASON)

    @field_validator("tool")
    @classmethod
    def _tool_name(cls, value: str) -> str:
        if value not in ALLOWED_AGENT_TOOLS:
            raise ValueError(f"unknown governed tool: {value}")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_text(cls, value: str) -> str:
        return redact_secrets(value)

    @field_validator("args")
    @classmethod
    def _bounded_args(cls, value: dict[str, Any]) -> dict[str, Any]:
        found = _contains_source_key(value)
        if found:
            raise SourcePayloadError(f"source-bearing plan argument {found!r} is not allowed")
        if len(canonical_json(value)) > MAX_STEP_ARGS_BYTES:
            raise ValueError(f"tool arguments exceed {MAX_STEP_ARGS_BYTES} bytes")
        return value


class InferencePlan(BaseModel):
    """Validated plan returned by the gateway and executed by the sandbox."""

    model_config = ConfigDict(extra="forbid")

    done: bool = False
    steps: list[PlanStep] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)


class InferenceProvenance(BaseModel):
    """Signed receipt metadata for hosted inference calls."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["gateway", "direct"]
    protocol_version: int = Field(default=INFERENCE_PROTOCOL_VERSION, ge=1)
    gateway_url: Optional[str] = Field(default=None, max_length=512)
    gateway_version: Optional[str] = Field(default=None, max_length=64)
    model: str = Field(max_length=128)
    requests: int = Field(default=0, ge=0, le=1000)
    observations_sent: int = Field(default=0, ge=0, le=100000)
    source_code_included: Literal[False] = False
    observation_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    prompt_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    response_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    request_ids: list[str] = Field(default_factory=list, max_length=32)
    error: Optional[str] = Field(default=None, max_length=512)
    # Cost/benchmark capture (per run, aggregated across planner calls).
    # Optional and defaulted so pre-benchmark receipts stay schema-valid.
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    inference_seconds: float = Field(default=0.0, ge=0.0)

    @field_validator("gateway_url")
    @classmethod
    def _gateway_url_is_http(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("gateway_url must be an absolute http(s) URL")
        return value


class InferenceGatewayResponse(BaseModel):
    """Wire response from the control-plane inference gateway."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=INFERENCE_PROTOCOL_VERSION, ge=1, le=1)
    plan: InferencePlan
    provenance: InferenceProvenance


def sanitize_observations(observations: list[Mapping[str, Any]]) -> list[RuntimeObservation]:
    """Validate and sanitize observations before any network transmission."""
    if len(observations) > MAX_OBSERVATIONS:
        raise ValueError(f"at most {MAX_OBSERVATIONS} observations may be sent")
    sanitized: list[RuntimeObservation] = []
    for item in observations:
        if not isinstance(item, Mapping):
            raise ValueError("each observation must be an object")
        found = _contains_source_key(item)
        if found:
            raise SourcePayloadError(f"source-bearing observation field {found!r} is not allowed")
        sanitized.append(RuntimeObservation.model_validate(item))
    return sanitized


def parse_plan_text(content: str) -> InferencePlan:
    """Parse a model response containing a JSON plan, tolerating markdown fences."""
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response contains no JSON plan")
    plan = json.loads(text[start : end + 1])
    return InferencePlan.model_validate(plan)


__all__ = [
    "ALLOWED_AGENT_TOOLS",
    "InferenceBudget",
    "InferenceGatewayRequest",
    "InferenceGatewayResponse",
    "InferencePlan",
    "InferenceProvenance",
    "InferenceProtocolError",
    "INFERENCE_PROTOCOL_VERSION",
    "MAX_PROMPT_BYTES",
    "MAX_OBSERVATIONS",
    "PlanStep",
    "RuntimeObservation",
    "SourcePayloadError",
    "canonical_json",
    "parse_plan_text",
    "redact_secrets",
    "sanitize_observations",
    "sha256_json",
]


class InferenceProtocolError(ValueError):
    """Compatibility alias for callers that classify protocol failures."""
