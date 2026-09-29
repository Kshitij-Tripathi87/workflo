"""Test result and run summary models — produced by the Worker, stored by the Backend."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A first-class Workflo finding: evidence-backed, severity-classified.

    Hard rule (contract §5): a finding's AUTHORITY comes only from
    `evidence_refs` — event IDs in the hash-chained evidence ledger.
    `agent_reasoning` is the LLM planner's interpretation; it is never
    trusted as proof. `confidence` is only present for agent-sourced
    findings, so it can't manufacture certainty without a runtime source.
    `status='confirmed'` requires the finding be provable from the
    ephemeral findings log; `reported` means the observed behavior is
    ambiguous under the agent's current evidence.
    """

    finding_id: str = Field(
        description="Deterministic ID (e.g. wf-fnd-<hash>): stable across "
        "runs for the same underlying issue."
    )
    title: str
    severity: str = Field(default="info")  # info | low | medium | high | critical
    status: str = Field(default="reported")  # reported | confirmed | informational
    summary: str = ""
    confidence: Optional[float] = Field(
        default=None,
        description="0.0–1.0, agent-computed. Absent for deterministic/"
        "host-observed findings; present only for LLM-planner output."
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Event IDs (evt_*) from the evidence ledger proof.",
    )
    reproduction: Optional[dict] = Field(
        default=None,
        description="How to reproduce (method, path, payload) if any.",
    )
    agent_reasoning: Optional[str] = Field(
        default=None,
        description="LLM planner's explanation. Never proof — always "
        "contrasted with evidence_refs.",
    )


class TestResult(BaseModel):
    nodeid: str = Field(description="pytest node ID, e.g. tests/security/test_tenant_isolation.py::TestTenantIsolation::test_x")
    status: str = Field(description="passed | failed | skipped | deselected")
    duration: float = Field(description="Execution time in seconds")
    markers: list[str] = Field(default_factory=list)
    soc2_controls: list[str] = Field(default_factory=list, description="e.g. ['CC6.1', 'CC6.6']")
    assertion: str = Field(default="", description="Human-readable assertion description")
    tenant_pair: list[str] = Field(default_factory=list)
    pattern: Optional[str] = None
    actual_status: Optional[int] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None
    timestamp: Optional[datetime] = None


class RunSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    deselected: int = 0
    positive_controls_passed: int = 0
    duration_seconds: float = 0.0
    soc2_controls: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    collection_error: Optional[str] = Field(
        default=None,
        description="Present when pytest exited abnormally (collection error, "
        "internal error) or exited nonzero with no tests collected. A run "
        "that never actually ran the repo's tests must not report a clean "
        "0/0 — the cause goes here.",
    )

    @property
    def pass_rate_pct(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.passed / self.total) * 100, 2)
