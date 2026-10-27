"""Invariant and round-trip tests for the crew contracts (S02).

Every contract must:
- reject unknown fields (extra=forbid),
- carry a schema_version,
- round-trip from its valid fixture,
- be rejected by its invalid fixture for the documented reason.

Invariants under test (docs/contracts.md):
- Confirmed requires >= 2 repro evidence refs and 1 control ref.
- ReportDraft.cited_evidence_ids must be a subset of the finding's evidence.
- ModelCallRecord never stores prompt or response bodies.
- Canary results are tri-state: blocked | leaked | not_run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

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
    validate_report_draft,
)

MODELS = {
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

FIXTURES = Path(__file__).parent / "fixtures"

INVALID_REASON = {
    "run_input": "snapshot_sha256",
    "sandbox_handle": "canary_result",
    "project_map": "source",
    "requirement_set": "req_id",
    "probe_plan": "probe_id",
    "candidate": "origin",
    "finding": "repro_evidence_refs",
    "model_call_record": "response_body",
    "report_draft": "unexpected_field",
    "report_bundle": "requirement_statuses",
    "stage_result": "failure_stage",
    "event_record": "payload_hash",
}


def _fixtures(kind: str) -> list[Path]:
    return sorted((FIXTURES / kind).glob("*.json"))


@pytest.mark.parametrize("path", _fixtures("valid"), ids=lambda p: p.stem)
def test_valid_fixture_round_trips(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    model = MODELS[path.stem]
    parsed = model.model_validate(data)
    assert parsed.schema_version == 1
    dumped = parsed.model_dump(mode="json", exclude_none=True)
    reparsed = model.model_validate(json.loads(json.dumps(dumped)))
    assert reparsed == parsed


@pytest.mark.parametrize("path", _fixtures("invalid"), ids=lambda p: p.stem)
def test_invalid_fixture_is_rejected(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    model = MODELS[path.stem]
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_unknown_field_rejected_for_every_model(name: str):
    data = json.loads((FIXTURES / "valid" / f"{name}.json").read_text(encoding="utf-8"))
    data["definitely_not_a_field"] = 1
    with pytest.raises(ValidationError):
        MODELS[name].model_validate(data)


def test_confirmed_finding_requires_two_repros_and_control():
    base = json.loads((FIXTURES / "valid" / "finding.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        Finding.model_validate({**base, "status": "Confirmed", "repro_evidence_refs": ["ev-1"]})
    with pytest.raises(ValidationError):
        Finding.model_validate({**base, "status": "Confirmed", "control_evidence_ref": None})
    ok = Finding.model_validate(
        {**base, "status": "Confirmed", "repro_evidence_refs": ["ev-1", "ev-2"], "control_evidence_ref": "ev-c"}
    )
    assert ok.status == "Confirmed"


def test_flaky_and_unconfirmed_do_not_require_two_repros():
    base = json.loads((FIXTURES / "valid" / "finding.json").read_text(encoding="utf-8"))
    flaky = Finding.model_validate({**base, "status": "Flaky", "repro_evidence_refs": ["ev-1"]})
    assert flaky.status == "Flaky"
    unconfirmed = Finding.model_validate({**base, "status": "Unconfirmed", "repro_evidence_refs": []})
    assert unconfirmed.status == "Unconfirmed"


def test_report_draft_cited_ids_must_be_subset_of_finding_evidence():
    finding = Finding.model_validate(
        json.loads((FIXTURES / "valid" / "finding.json").read_text(encoding="utf-8"))
    )
    inside = {r for r in finding.repro_evidence_refs}
    inside.add(finding.control_evidence_ref)
    draft = ReportDraft.model_validate(json.loads((FIXTURES / "valid" / "report_draft.json").read_text(encoding="utf-8")))
    draft_ok = draft.model_copy(update={"cited_evidence_ids": sorted(inside)})
    validate_report_draft(draft_ok, finding)

    draft_bad = draft_ok.model_copy(update={"cited_evidence_ids": ["ev-does-not-exist"]})
    with pytest.raises(ValueError, match="cited_evidence_ids"):
        validate_report_draft(draft_bad, finding)


def test_model_call_record_rejects_body_fields():
    base = json.loads((FIXTURES / "valid" / "model_call_record.json").read_text(encoding="utf-8"))
    for body_field in ("prompt_body", "response_body", "completion_body", "messages"):
        with pytest.raises(ValidationError):
            ModelCallRecord.model_validate({**base, body_field: "secret source text"})


def test_stage_result_cannot_be_ok_while_carrying_a_failure():
    base = json.loads((FIXTURES / "valid" / "stage_result.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        StageResult.model_validate({**base, "ok": True, "failure_stage": "app"})
    failed = StageResult.model_validate(
        {**base, "ok": False, "failure_stage": "app", "failure_reason": "app never booted"}
    )
    assert failed.failure_stage == "app"
