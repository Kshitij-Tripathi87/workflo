#!/usr/bin/env python3
"""Create metadata-only unit-economics evidence from benchmark reports."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


class CostEvidenceError(ValueError):
    """The benchmark set cannot support a release cost estimate."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="append", type=Path, required=True)
    parser.add_argument("--instance-hourly-usd", type=float, required=True)
    parser.add_argument("--representative-requests", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report: dict = {"passed": False, "failure_class": None}
    try:
        rate = args.instance_hourly_usd
        if not math.isfinite(rate) or rate < 0:
            raise CostEvidenceError("hourly assumption must be finite and non-negative")
        if args.representative_requests < 1:
            raise CostEvidenceError("representative request count must be positive")

        total_seconds = 0.0
        completed = 0
        requested = 0
        for path in args.benchmark:
            value = json.loads(path.read_text(encoding="utf-8"))
            assumption = float(value["assumptions"]["instance_hourly_usd"])
            if assumption != rate:
                raise CostEvidenceError("benchmark hourly assumptions do not match")
            levels = value.get("levels")
            if not isinstance(levels, list) or not levels:
                raise CostEvidenceError("benchmark has no concurrency levels")
            for level in levels:
                total_seconds += float(level["wall_seconds"])
                completed += int(level["succeeded"])
                requested += int(level["requests"])
                if int(level["failed"]) != 0:
                    raise CostEvidenceError("failed benchmark requests cannot support cost evidence")
        if completed < 1 or completed != requested or total_seconds <= 0:
            raise CostEvidenceError("benchmark completion evidence is incomplete")

        estimated_total = rate * total_seconds / 3600.0
        estimated_per_request = estimated_total / completed
        report = {
            "passed": True,
            "assumption_instance_hourly_usd": rate,
            "benchmark_repeats": len(args.benchmark),
            "benchmark_seconds": round(total_seconds, 6),
            "requests_completed": completed,
            "requests_requested": requested,
            "estimated_total_benchmark_usd": round(estimated_total, 8),
            "estimated_cost_per_request_usd": round(estimated_per_request, 8),
            "representative_run_requests": args.representative_requests,
            "estimated_cost_per_representative_run_usd": round(
                estimated_per_request * args.representative_requests, 8
            ),
        }
    except (CostEvidenceError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        report["failure_class"] = type(exc).__name__

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report["passed"]:
        print(f"cost evidence failed ({report['failure_class']})", file=sys.stderr)
        return 1
    print("metadata-only benchmark cost evidence passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
