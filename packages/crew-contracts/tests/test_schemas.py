"""The committed JSON Schemas must never drift from the models."""

from __future__ import annotations

import json
from pathlib import Path

from workflo_crew_contracts import export as schema_export

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def test_every_contract_has_a_committed_schema():
    for name in schema_export.CONTRACTS:
        assert (SCHEMAS / f"{name}.json").exists(), f"missing schema for {name}"


def test_committed_schemas_match_models(tmp_path: Path):
    written = schema_export.export(tmp_path)
    assert len(written) == len(schema_export.CONTRACTS)
    for name, model in schema_export.CONTRACTS.items():
        committed = json.loads((SCHEMAS / f"{name}.json").read_text(encoding="utf-8"))
        assert committed == model.model_json_schema(), f"schema drift for {name}"
