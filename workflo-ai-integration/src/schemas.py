"""
Structured output schemas for the three task-specific LoRA adapters.

Design principle: the model never gets to assert a result directly. It only
ever proposes one of these typed objects. Each one has to pass validation
(and, for code, a compile check) before it's allowed anywhere near real
execution. A malformed or hallucinated response fails loudly here, not
silently downstream in a customer-facing report.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class WriteTestCall(BaseModel):
    """Output of the test-generation adapter (--deep-test)."""

    path: str = Field(..., description="Relative path for the generated test file")
    content: str = Field(..., min_length=1, description="Full Python source of the test file")
    framework: Literal["pytest"] = "pytest"
    rationale: str = Field(..., description="One-sentence reason this test was generated")

    @field_validator("path")
    @classmethod
    def path_must_be_test_file(cls, v: str) -> str:
        if not (v.startswith("test_") or "/test_" in v or v.endswith("_test.py")):
            raise ValueError(f"generated path '{v}' does not look like a pytest test file")
        if ".." in v or v.startswith("/"):
            raise ValueError(f"generated path '{v}' escapes the sandbox working directory")
        return v


class ProposeInvariantCall(BaseModel):
    """
    Output of the security/reasoning adapter, used for both --security
    (tenant-isolation invariants) and --aggressive-test (general business-logic
    invariants). Both are the same underlying task: "what should always be
    true here, and how do we check it."
    """

    description: str = Field(..., description="Plain-English statement of the invariant")
    target: str = Field(..., description="Route, function, or module the invariant applies to")
    category: Literal["tenant_isolation", "business_logic", "data_integrity", "auth"] = "business_logic"
    hypothesis_strategy: str = Field(
        ..., description="A Hypothesis @given(...) strategy expression to generate test inputs"
    )
    property_check: str = Field(
        ..., description="Python assertion expression checking the invariant holds"
    )


class ReportFinding(BaseModel):
    root_cause: str
    affected_tests: list[str]
    severity: Literal["info", "low", "medium", "high"]
    explanation: str


class ReportNarrative(BaseModel):
    """
    Output of the reporting adapter. Takes ONLY structured JSON test results
    as input (never raw source), so this is the lowest-risk adapter from a
    privacy standpoint — nothing here can leak source code because none was
    ever in its context.
    """

    summary: str = Field(..., description="2-3 sentence plain-English run summary")
    findings: list[ReportFinding] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=list, description="Finding root_causes ordered by what to fix first"
    )
