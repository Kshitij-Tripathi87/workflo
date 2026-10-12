#!/usr/bin/env python3
"""Fail-closed validation of the adapter training datasets.

Every assistant payload must validate against the exact Pydantic schemas the
serving router enforces, and every executable fragment must pass the exact
safety gates the router applies at request time:

  - test_gen:    WriteTestCall + compile_check(content)
  - reasoning:   ProposeInvariantCall + property_expr_check(strategy) and
                 property_expr_check(property_check)
  - reporting:   ReportNarrative

A dataset that fails here must never reach a training run: teaching the model
output that the serving gates reject would train it to produce garbage the
router discards.

Usage:
    python train/validate_datasets.py [--train-dir train]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from workflo_ai_integration.safety_gate import (  # noqa: E402
    compile_check,
    property_expr_check,
)
from workflo_ai_integration.schemas import (  # noqa: E402
    ProposeInvariantCall,
    ReportNarrative,
    WriteTestCall,
)

SCHEMA_BY_TASK = {
    "test_gen": WriteTestCall,
    "reasoning": ProposeInvariantCall,
    "reporting": ReportNarrative,
}


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    schema_cls = SCHEMA_BY_TASK[path.stem]
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        label = f"{path.name}:{lineno}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label}: invalid JSON line: {exc}")
            continue
        for field in ("system", "user", "assistant"):
            if not isinstance(record.get(field), str) or not record[field]:
                errors.append(f"{label}: missing or empty '{field}'")
        if errors and errors[-1].startswith(label):
            continue
        try:
            payload = json.loads(record["assistant"])
        except json.JSONDecodeError as exc:
            errors.append(f"{label}: assistant is not valid JSON: {exc}")
            continue
        try:
            obj = schema_cls.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError
            errors.append(f"{label}: schema validation failed: {exc}")
            continue
        if isinstance(obj, WriteTestCall):
            result = compile_check(obj.content)
            if not result.ok:
                errors.append(f"{label}: compile gate rejected content: {result.reason}")
            else:
                try:
                    ast.parse(obj.content)
                except (SyntaxError, ValueError) as exc:
                    errors.append(f"{label}: content does not parse: {exc}")
        elif isinstance(obj, ProposeInvariantCall):
            for field_name in ("hypothesis_strategy", "property_check"):
                result = property_expr_check(getattr(obj, field_name))
                if not result.ok:
                    errors.append(
                        f"{label}: expression gate rejected {field_name}: "
                        f"{result.reason}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()
    datasets_dir = args.train_dir / "datasets"
    all_errors: list[str] = []
    for task in SCHEMA_BY_TASK:
        path = datasets_dir / f"{task}.jsonl"
        if not path.is_file():
            all_errors.append(f"missing dataset file: {path}")
            continue
        all_errors.extend(validate_file(path))
    if all_errors:
        for error in all_errors:
            print(f"FAIL {error}", file=sys.stderr)
        print(f"dataset validation failed: {len(all_errors)} error(s)", file=sys.stderr)
        return 1
    total = sum(
        len(
            [
                line
                for line in (datasets_dir / f"{task}.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
        )
        for task in SCHEMA_BY_TASK
    )
    print(f"dataset validation passed: {total} examples across 3 tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
