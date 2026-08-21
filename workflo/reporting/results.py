"""Results schema emitted by the Tenant Shield pytest plugin.

Matches the JSON schema described in the Phase 1.6 plan:

    {
      "test_run_id": "uuid",
      "timestamp": "2026-07-23T...",
      "suite": "tenant-isolation",
      "results": [
        {
          "test_name": "...",
          "status": "passed",
          "assertion": "Company2 GET /api/v1/projects/{id} -> (403, 404)",
          "tenant_pair": ["company1", "company2"],
          "soc2_controls": ["CC6.1", "CC6.6"],
          "screenshot_path": null
        }
      ],
      "summary": {"total": 10, "passed": 10, "failed": 0, "positive_controls_passed": 5}
    }
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class
    test_name: str
    nodeid: str
    status: str
    duration: float = 0.0
    markers: List[str] = field(default_factory=list)
    assertion: str = ""
    tenant_pair: List[str] = field(default_factory=lambda: [])
    soc2_controls: List[str] = field(default_factory=list)
    pattern: Optional[str] = None
    expected_denial: str = ""
    actual_status: Optional[int] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunReport:
    test_run_id: str
    timestamp: str
    suite: str
    results: List[TestResult] = field(default_factory=list)

    @classmethod
    def new(cls, suite: str = "tenant-isolation") -> "RunReport":
        return cls(
            test_run_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            suite=suite,
        )

    @property
    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "passed")
        failed = sum(1 for r in self.results if r.status == "failed")
        skipped = sum(1 for r in self.results if r.status == "skipped")
        pc = sum(
            1
            for r in self.results
            if r.pattern == "positive_control" and r.status == "passed"
        )
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "positive_controls_passed": pc,
        }

    def to_dict(self) -> dict:
        return {
            "test_run_id": self.test_run_id,
            "timestamp": self.timestamp,
            "suite": self.suite,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "RunReport":
        rr = cls(
            test_run_id=data.get("test_run_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            suite=data.get("suite", "tenant-isolation"),
        )
        for r in data.get("results", []):
            rr.results.append(TestResult(**r))
        return rr

    @classmethod
    def from_json_file(cls, path: str) -> "RunReport":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
