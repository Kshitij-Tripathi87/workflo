"""Declarative probe models — the contract between config and execution.

A ProbeSpec describes one assertion to run against an unknown repo.
A ProbeConfig is a set of ProbeSpecs loaded from YAML.
A ProbeResult is what one probe returns after being executed.
A ProbeRunSummary aggregates results across all probes in a config.
"""

from __future__ import annotations

from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class ProbeSpec(BaseModel):
    """One declarative probe — replace one hardcoded isolation test."""

    name: str = Field(description="Unique, human-readable probe name")
    pattern: str = Field(
        description="IsolationPattern name: api_read, api_list, api_modify, "
        "api_delete, ui_visibility, ui_invisibility, positive_control"
    )
    path: str = Field(description="API path to probe, e.g. /api/v1/projects")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, DELETE")
    expected_status: Union[int, list[int]] = Field(
        default=403,
        description="Status code(s) that mean the probe passed",
    )
    list_key: Optional[str] = Field(
        default=None,
        description="For api_list: the JSON key containing the list to inspect",
    )
    expect_resource_absent: bool = Field(
        default=False,
        description="For api_list: True if the target resource must NOT appear in the list",
    )
    soc2_controls: list[str] = Field(
        default_factory=list,
        description="SOC 2 controls this probe maps to",
    )
    description: str = Field(default="", description="Human-readable probe description")


class ProbeResult(BaseModel):
    """Result of executing one probe."""

    name: str
    pattern: str
    method: str
    path: str
    actual_status: Optional[int] = None
    passed: bool = False
    error: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ProbeConfig(BaseModel):
    """A full config — a list of probe specs + metadata."""

    name: str = Field(default="default", description="Config name")
    version: str = Field(default="1.0", description="Config schema version")
    probes: list[ProbeSpec] = Field(default_factory=list)
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs (e.g. repo_url, commit_sha)",
    )

    @classmethod
    def from_yaml_str(cls, yaml_str: str) -> "ProbeConfig":
        """Parse a YAML string into a ProbeConfig."""
        import yaml
        data = yaml.safe_load(yaml_str)
        return cls(**data)


class ProbeRunSummary(BaseModel):
    """Aggregated outcome of running all probes in a config.

    This is what the sandbox executor turns into a RunReport.
    """

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    soc2_controls_covered: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    results: list[ProbeResult] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.passed > 0
