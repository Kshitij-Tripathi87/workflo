"""Structured record of a single isolation assertion.

A `VerificationRecord` is produced by the verifier / scenario for every
assertion made. Records feed both test failures (rich messages) and the
SOC 2 evidence report (machine-readable JSON).
"""

from dataclasses import dataclass, field, asdict
from typing import Any, List, Optional


@dataclass
class VerificationRecord:
    pattern: str
    assertion: str
    expected: Any
    actual_status: Optional[int]
    passed: bool
    tenant_pair: List[str]
    resource_id: Optional[str] = None
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationSummary:
    """Aggregated outcome of all assertions for one resource isolation run."""

    creator_tenant: str
    intruder_tenant: str
    resource_id: str
    records: List[VerificationRecord] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.records)

    @property
    def soc2_controls(self) -> List[str]:
        controls = []
        for r in self.records:
            for c in r.evidence.get("soc2_controls", []):
                if c not in controls:
                    controls.append(c)
        return controls

    def to_dict(self) -> dict:
        return {
            "creator_tenant": self.creator_tenant,
            "intruder_tenant": self.intruder_tenant,
            "resource_id": self.resource_id,
            "passed": self.passed,
            "records": [r.to_dict() for r in self.records],
        }
