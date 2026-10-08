"""JSON reporter — full machine-readable summary."""

from __future__ import annotations

import json
from pathlib import Path

from ..orchestrator import ValidationResult


def write(result: ValidationResult, out_path: Path) -> None:
    """Write a JSON file with gates + findings + summary."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_summary_dict()
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
