"""Structured, fail-closed outputs for the task-specific llama.cpp adapters."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WriteTestCall(BaseModel):
    """Output of the test-generation adapter (``--deep-test``)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        ...,
        min_length=1,
        max_length=240,
        description="Relative POSIX path for a generated pytest file",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=256 * 1024,
        description="Full Python source of the test file",
    )
    framework: Literal["pytest"] = "pytest"
    rationale: str = Field(..., min_length=1, max_length=1024)

    @field_validator("path")
    @classmethod
    def path_must_be_safe_test_file(cls, value: str) -> str:
        """Reject absolute, platform-ambiguous, and traversal paths.

        The caller still resolves the final destination under its dedicated
        generated-test directory. This validator is the first of two path
        boundaries, not a replacement for destination containment checks.
        """
        if "\x00" in value or "\\" in value:
            raise ValueError("generated path must be a POSIX relative path")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("generated path escapes the generated-test directory")
        if path.suffix != ".py":
            raise ValueError("generated test path must end in .py")
        if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            raise ValueError(f"generated path '{value}' does not name a pytest test file")
        return path.as_posix()


class ProposeInvariantCall(BaseModel):
    """Output of the security/reasoning adapter."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., min_length=1, max_length=2048)
    target: str = Field(..., min_length=1, max_length=512)
    category: Literal[
        "tenant_isolation", "business_logic", "data_integrity", "auth"
    ] = "business_logic"
    hypothesis_strategy: str = Field(..., min_length=1, max_length=4096)
    property_check: str = Field(..., min_length=1, max_length=4096)


class ReportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_cause: str = Field(..., min_length=1, max_length=2048)
    affected_tests: list[str] = Field(default_factory=list, max_length=100)
    severity: Literal["info", "low", "medium", "high"]
    explanation: str = Field(..., min_length=1, max_length=4096)


class ReportNarrative(BaseModel):
    """Reporting output; input is structured results and never source."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, max_length=4096)
    findings: list[ReportFinding] = Field(default_factory=list, max_length=100)
    priority_order: list[str] = Field(default_factory=list, max_length=100)
