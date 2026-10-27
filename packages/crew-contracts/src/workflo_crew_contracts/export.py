"""Export JSON Schema for every crew contract.

Usage:
    python -m workflo_crew_contracts.export [--out schemas]

Writes one ``<Model>.json`` per contract into the target directory
(default: <package>/schemas). The test suite re-exports to a temp dir and
compares, so committed schemas cannot drift from the models.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflo_crew_contracts import (
    Candidate,
    EventRecord,
    Finding,
    ModelCallRecord,
    ProjectMap,
    ProbePlan,
    ReportBundle,
    ReportDraft,
    RequirementSet,
    RunInput,
    SandboxHandle,
    StageResult,
)

CONTRACTS: dict[str, type] = {
    "run_input": RunInput,
    "sandbox_handle": SandboxHandle,
    "project_map": ProjectMap,
    "requirement_set": RequirementSet,
    "probe_plan": ProbePlan,
    "candidate": Candidate,
    "finding": Finding,
    "model_call_record": ModelCallRecord,
    "report_draft": ReportDraft,
    "report_bundle": ReportBundle,
    "stage_result": StageResult,
    "event_record": EventRecord,
}


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in sorted(CONTRACTS.items()):
        schema = model.model_json_schema()
        target = out_dir / f"{name}.json"
        target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = Path(__file__).resolve().parents[2] / "schemas"
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()
    for path in export(args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
