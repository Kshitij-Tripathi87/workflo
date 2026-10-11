#!/usr/bin/env python3
"""Reduce an expected failed inference benchmark to source-free evidence."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ERROR_CLASS = re.compile(
    r"^(?:transport_[A-Za-z][A-Za-z0-9_]*|http_status_[1-5][0-9]{2}|"
    r"invalid_[a-z0-9_]+|cross_request_leakage|isolation_marker_missing)$"
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--command-exit-code", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    evidence: dict = {"passed": False, "failure_class": None}
    try:
        raw = json.loads(args.raw.read_text(encoding="utf-8"))
        if args.command_exit_code == 0:
            raise ValueError("failure probe unexpectedly succeeded")
        endpoint = raw.get("endpoint_sha256")
        if not isinstance(endpoint, str) or not HEX64.fullmatch(endpoint):
            raise ValueError("failure probe endpoint identity is invalid")
        levels = raw.get("levels")
        if not isinstance(levels, list) or len(levels) != 1:
            raise ValueError("failure probe must contain exactly one level")
        level = levels[0]
        errors = level.get("errors")
        if not isinstance(errors, list) or not errors:
            raise ValueError("failure probe retained no error identities")
        if any(not isinstance(error, str) or not ERROR_CLASS.fullmatch(error) for error in errors):
            raise ValueError("failure probe retained a non-classified error")
        if int(level.get("succeeded", -1)) != 0 or int(level.get("failed", 0)) < 1:
            raise ValueError("failure probe outcome is not fail-closed")
        evidence = {
            "passed": True,
            "inference_succeeded": False,
            "command_exit_nonzero": True,
            "endpoint_sha256": endpoint,
            "model": raw.get("model"),
            "concurrency": int(level.get("concurrency", 0)),
            "requests": int(level.get("requests", 0)),
            "failed": int(level.get("failed", 0)),
            "elapsed_seconds": float(level.get("wall_seconds", 0.0)),
            "error_classes": sorted(set(errors)),
            "source_code_included": False,
            "prompt_recorded": False,
            "generated_code_recorded": False,
            "narrative_recorded": False,
            "credentials_recorded": False,
        }
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        evidence["failure_class"] = type(exc).__name__

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not evidence["passed"]:
        print(f"safe-failure evidence failed ({evidence['failure_class']})", file=sys.stderr)
        return 1
    print("safe inference failure retained only classified metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
