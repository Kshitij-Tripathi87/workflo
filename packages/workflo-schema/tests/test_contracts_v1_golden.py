"""Synthetic wire records shared with the TypeScript contract and ledger tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from workflo_schema.contracts import RunOutcomeV1, canonical_json, digest_of, is_clean_success, is_full_pass

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "v1-golden.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("example", GOLDEN["outcomes"].values(), ids=GOLDEN["outcomes"].keys())
def test_normalized_outcome_record(example: dict) -> None:
    outcome = RunOutcomeV1.model_validate(example["record"])
    assert outcome.model_dump(mode="json") == example["record"]
    assert is_clean_success(outcome) is example["clean_success"]
    assert is_full_pass(outcome) is example["full_pass"]


@pytest.mark.parametrize("example", GOLDEN["invalid_outcomes"], ids=lambda example: example["name"])
def test_invalid_outcome_record(example: dict) -> None:
    base = GOLDEN["outcomes"][example["base"]]["record"]
    with pytest.raises(ValidationError):
        RunOutcomeV1.model_validate(base | example["overrides"])


@pytest.mark.parametrize("example", GOLDEN["canonical_json"], ids=lambda example: example["name"])
def test_canonical_json_bytes_and_digest(example: dict) -> None:
    assert canonical_json(example["payload"]) == example["canonical"]
    assert digest_of(example["payload"]) == example["digest"]
