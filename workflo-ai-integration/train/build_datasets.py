#!/usr/bin/env python3
"""Serialize dataset_sources.py into ChatML JSONL files under datasets/.

Run from the train/ directory (or anywhere, paths are package-relative):

    python train/build_datasets.py

Output line format (one JSON object per line):
    {"system": "...", "user": "...", "assistant": "<compact JSON>"}

The assistant value is compact JSON matching the adapter's Pydantic schema,
exactly what the serving router validates after generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TRAIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TRAIN_DIR))

import dataset_sources as sources  # noqa: E402

TASKS = {
    "test_gen": (sources.TEST_GEN_SYSTEM, sources.TEST_GEN),
    "reasoning": (sources.REASONING_SYSTEM, sources.REASONING),
    "reporting": (sources.REPORTING_SYSTEM, sources.REPORTING),
}


def main() -> int:
    out_dir = TRAIN_DIR / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (system, examples) in TASKS.items():
        lines = []
        for record in examples:
            lines.append(
                json.dumps(
                    {
                        "system": system,
                        "user": record["user"],
                        "assistant": json.dumps(
                            record["assistant"], sort_keys=True
                        ),
                    },
                    sort_keys=True,
                )
            )
        target = out_dir / f"{name}.jsonl"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {len(lines)} examples -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
