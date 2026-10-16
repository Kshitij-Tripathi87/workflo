#!/usr/bin/env python3
"""Deterministic stratified-by-position train/eval split for one task.

The retrain plan's held-out split: 90/10 per task, selected as evenly spaced
indices (seed-independent and reviewable), so the eval set spans both the
original and the newly authored examples.

Usage:
    python train/split_dataset.py \
        --input train/datasets/reasoning.jsonl \
        --out-train train/datasets/splits/reasoning_train.jsonl \
        --out-eval train/datasets/splits/reasoning_eval.jsonl \
        --eval-indices 9,19,29,39
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-train", required=True, type=Path)
    parser.add_argument("--out-eval", required=True, type=Path)
    parser.add_argument("--eval-indices", required=True,
                        help="comma-separated 0-based indices held out for eval")
    args = parser.parse_args()

    eval_indices = {int(i) for i in args.eval_indices.split(",")}
    records = [
        line
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for index in eval_indices:
        if index < 0 or index >= len(records):
            raise ValueError(
                f"eval index {index} out of range for {len(records)} records"
            )

    args.out_train.parent.mkdir(parents=True, exist_ok=True)
    train_lines = [
        record for position, record in enumerate(records) if position not in eval_indices
    ]
    eval_lines = [
        record for position, record in enumerate(records) if position in eval_indices
    ]
    args.out_train.write_text("\n".join(train_lines) + "\n", encoding="utf-8")
    args.out_eval.write_text("\n".join(eval_lines) + "\n", encoding="utf-8")
    print(
        f"{args.input.name}: {len(train_lines)} train / {len(eval_lines)} eval "
        f"(held out at {sorted(eval_indices)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
