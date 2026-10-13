"""Contract harness: the 57 authoritative ChatML examples must satisfy the
exact serving schemas and safety gates, and the serving system prompts must
be byte-identical to the training prompts.

This is the product-side guard requested for the sprint: if the training
data, the schemas, or the serving prompts ever drift apart, this test fails
before a model can be retrained or served against a mismatched contract.
"""

import json
from pathlib import Path

import pytest
from workflo_ai_integration.safety_gate import compile_check, property_expr_check
from workflo_ai_integration.schemas import (
    ProposeInvariantCall,
    ReportNarrative,
    WriteTestCall,
)
from workflo_ai_integration.service_defaults import SYSTEM_PROMPTS

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DATASETS = PACKAGE_ROOT / "train" / "datasets"

TASK_FILES = {
    "test_gen": ("test_gen.jsonl", WriteTestCall),
    "reasoning": ("reasoning.jsonl", ProposeInvariantCall),
    "reporting": ("reporting.jsonl", ReportNarrative),
}

EXPECTED_COUNTS = {"test_gen": 20, "reasoning": 20, "reporting": 17}


def _load(task: str) -> list[dict]:
    filename, _ = TASK_FILES[task]
    path = DATASETS / filename
    assert path.is_file(), f"missing training dataset: {path}"
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        assert set(record) == {"system", "user", "assistant"}, (
            f"{filename}:{lineno} must have exactly system/user/assistant keys"
        )
        records.append(record)
    return records


def test_all_57_examples_exist():
    total = 0
    for task in TASK_FILES:
        records = _load(task)
        assert len(records) == EXPECTED_COUNTS[task], (
            f"{task}: expected {EXPECTED_COUNTS[task]} examples, found {len(records)}"
        )
        total += len(records)
    assert total == 57


@pytest.mark.parametrize("task", sorted(TASK_FILES))
def test_example_payloads_validate_against_serving_schemas(task):
    _, schema_cls = TASK_FILES[task]
    for record in _load(task):
        obj = schema_cls.model_validate(
            json.loads(record["assistant"])
            if isinstance(record["assistant"], str)
            else record["assistant"]
        )
        assert obj is not None


@pytest.mark.parametrize("task", sorted(TASK_FILES))
def test_example_payloads_pass_serving_safety_gates(task):
    for record in _load(task):
        payload = (
            json.loads(record["assistant"])
            if isinstance(record["assistant"], str)
            else record["assistant"]
        )
        if task == "test_gen":
            result = compile_check(payload["content"])
            assert result.ok, f"compile_check rejected training example: {result.reason}"
        elif task == "reasoning":
            for key in ("hypothesis_strategy", "property_check"):
                result = property_expr_check(payload[key])
                assert result.ok, f"property_expr_check rejected {key}: {result.reason}"


def test_serving_system_prompts_are_byte_identical_to_training_prompts():
    """Drift between training and serving prompts silently degrades adapter
    output quality — the adapters overfit to the training strings."""
    train_dir = str(PACKAGE_ROOT / "train")
    import sys

    if train_dir not in sys.path:
        sys.path.insert(0, train_dir)
    try:
        import dataset_sources as training_prompts
    finally:
        if train_dir in sys.path:
            sys.path.remove(train_dir)

    pairs = {
        "test-gen": training_prompts.TEST_GEN_SYSTEM,
        "reasoning": training_prompts.REASONING_SYSTEM,
        "reporting": training_prompts.REPORTING_SYSTEM,
    }
    for task, training_prompt in pairs.items():
        assert SYSTEM_PROMPTS[task] == training_prompt, (
            f"serving system prompt for {task} drifted from train/dataset_sources.py"
        )


def test_every_example_system_prompt_matches_task_default():
    """Per-example system prompts in the JSONL must also match the serving
    default for that task (records were built from the same source)."""
    task_key = {"test_gen": "test-gen", "reasoning": "reasoning", "reporting": "reporting"}
    for task in TASK_FILES:
        default = SYSTEM_PROMPTS[task_key[task]]
        for record in _load(task):
            assert record["system"] == default, (
                f"{task}: example system prompt differs from the serving default"
            )
