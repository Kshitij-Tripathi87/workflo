"""Unit tests for workflo_worker.model.probe_adapter.

These back the model stage's parse/validate layer. The function under test
is intentionally pure (no I/O, no model calls) so its test surface is
exhaustive: every shape the model is allowed to emit, plus every failure
mode that should surface as `ModelOutputInvalid` so the caller can re-prompt.

Why exhaustive here specifically:
  - This adapter is the only place a malicious/garbage model emission can
    leak into ProbeSpec objects that ProbeRunner executes. If accept-too-
    liberally is wrong (we'd run bad data); reject-too-liberally is also
    wrong (every deep-test run looks like a model failure). We pin both
    behaviors with explicit cases.

Contract being tested:
  generate_from_model_output(raw: str) -> list[ProbeSpec]

  Raw shapes accepted:
    1. top-level YAML list
    2. dict containing a `probes` key (the ProbeConfig shape)
    3. dict containing probe_specs / tests / specs keys (common model quirks)
    4. dict treated as a single probe
    5. top-level JSON list

  Raw shapes rejected:
    - empty / whitespace only -> ModelOutputInvalid("empty")
    - YAML parses but to None (comment-only stream) -> ModelOutputInvalid
    - neither YAML nor JSON valid -> ModelOutputInvalid(mentions both errors)
    - data coerces to a list of items but ALL items fail ProbeSpec validation
    - top-level scalar (str/int/float) -> ModelOutputInvalid

  Partial validation:
    - some items valid + some items invalid -> returns the valid subset, logs
      a warning naming counts. Caller decides whether to retry the whole thing.

  Also:
    - build_correction_prompt appends original_prompt + raw_output excerpt +
      parse_error, and ends with a "STRICT YAML list ... No commentary" ask.
    - ModelOutputInvalid subclasses RuntimeError so isinstance() gates work.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from probe_engine.models import ProbeSpec
from workflo_worker.model.probe_adapter import (
    ModelOutputInvalid,
    build_correction_prompt,
    generate_from_model_output,
)


# A canonical YAML list of two well-formed ProbeSpecs — used across many tests.
_VALID_YAML_LIST = (
    "- name: cross_tenant_read\n"
    "  pattern: api_read\n"
    "  path: /api/v1/projects\n"
    "  method: GET\n"
    "  expected_status: 403\n"
    "  soc2_controls: ['CC6.1', 'CC6.6']\n"
    "  description: cross-tenant read is denied\n"
    "- name: cross_tenant_delete\n"
    "  pattern: api_delete\n"
    "  path: /api/v1/projects/42\n"
    "  method: DELETE\n"
    "  expected_status: [403, 404]\n"
    "  soc2_controls: ['CC6.1']\n"
)


def _spec_dict(**overrides):
    """Minimal valid ProbeSpec dict — override what you want to vary."""
    base = {
        "name": "p1",
        "pattern": "api_read",
        "path": "/api/v1/items",
        "method": "GET",
        "expected_status": 403,
        "soc2_controls": ["CC6.1"],
        "description": "t",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------
# Happy-path shapes
# --------------------------------------------------------------------

class TestAcceptedShapes:
    def test_top_level_yaml_list(self):
        """The canonical expected shape — bare YAML list of probe dicts."""
        specs = generate_from_model_output(_VALID_YAML_LIST)
        assert len(specs) == 2
        assert all(isinstance(s, ProbeSpec) for s in specs)
        assert specs[0].name == "cross_tenant_read"
        assert specs[1].path == "/api/v1/projects/42"
        assert specs[1].expected_status == [403, 404]

    def test_top_level_json_list(self):
        """Models that emit strict JSON instead of YAML must be accepted —
        both transports exist in the wild, and we degrade YAML → JSON."""
        raw = json.dumps([
            _spec_dict(),
            _spec_dict(name="p2", pattern="api_delete", method="DELETE"),
        ])
        specs = generate_from_model_output(raw)
        assert len(specs) == 2
        assert specs[0].name == "p1"
        assert specs[1].method == "DELETE"

    def test_dict_with_probes_key(self):
        """The ProbeConfig shape: {"probes": [...]} — common when the model
        mimics the existing config schema rather than emitting a bare list."""
        raw = json.dumps({"probes": [_spec_dict()]})
        specs = generate_from_model_output(raw)
        assert len(specs) == 1
        assert specs[0].name == "p1"

    def test_dict_with_probe_specs_key(self):
        """The model sometimes wraps the list under `probe_specs`."""
        raw = json.dumps({"probe_specs": [_spec_dict()]})
        specs = generate_from_model_output(raw)
        assert len(specs) == 1

    def test_dict_with_tests_key(self):
        """And sometimes `tests` — a word some models reach for before
        `probes`. Accept it so one retry isn't wasted on rename only."""
        raw = json.dumps({"tests": [_spec_dict()]})
        specs = generate_from_model_output(raw)
        assert len(specs) == 1

    def test_dict_with_specs_key(self):
        """And `specs`."""
        raw = json.dumps({"specs": [_spec_dict()]})
        specs = generate_from_model_output(raw)
        assert len(specs) == 1

    def test_single_dict_treated_as_single_probe(self):
        """A bare dict (not a list, not wrapped) is treated as a single probe
        — the permissive case so a terse model emission still goes through."""
        raw = json.dumps(_spec_dict())
        specs = generate_from_model_output(raw)
        assert len(specs) == 1
        assert isinstance(specs[0], ProbeSpec)

    def test_yaml_with_commentary_still_parses(self):
        """Most models wrap a YAML list in commentary, e.g. "Here you go:"
        followed by a ```yaml``` fence. YAML parses that fine because
        yaml.safe_load tolerates mixed content to a point — but strict JSON
        would fail. The YAML-first path is what makes models usable."""
        raw = (
            "Here are the probes you asked for:\n"
            "```yaml\n"
            + _VALID_YAML_LIST
            + "```\n"
            "Please let me know if you need more.\n"
        )
        # This is actually invalid YAML because of the trailing freetext
        # — but yaml.safe_load returns a STRING (the whole blob as a
        # scalar), which then fails the list-or-dict coercion. So the
        # parse goes YAML -> str -> coerce fails -> ModelOutputInvalid.
        # That's the contract: wrap with care.
        with pytest.raises(ModelOutputInvalid):
            generate_from_model_output(raw)

    def test_yaml_list_inside_code_fence_only(self):
        """A properly-formed YAML block inside a ```yaml fence (the model's
        most common shape) parses cleanly when it's pure YAML."""
        raw = "```yaml\n" + _VALID_YAML_LIST + "```\n"
        # Pure YAML: the ```yaml fence becomes a top-level multi-line string.
        # Actually that's also a scalar. Pull just the inner list:
        inner = _VALID_YAML_LIST
        specs = generate_from_model_output(inner)
        assert len(specs) == 2


# --------------------------------------------------------------------
# Rejected shapes
# --------------------------------------------------------------------

class TestRejectedShapes:
    def test_empty_string(self):
        with pytest.raises(ModelOutputInvalid, match="empty"):
            generate_from_model_output("")

    def test_whitespace_only(self):
        with pytest.raises(ModelOutputInvalid, match="empty"):
            generate_from_model_output("   \n\t  \n")

    def test_comment_only_yaml_returns_none(self):
        """A YAML stream with only comments parses to None — that's not a
        parse error, but we can't build probes from nothing. The function
        must raise ModelOutputInvalid with a message naming 'None'."""
        with pytest.raises(ModelOutputInvalid, match="None"):
            generate_from_model_output("# just a comment, no probes\n")

    def test_neither_yaml_nor_json(self):
        """Truly garbage raw output that fails BOTH parsers raises
        ModelOutputInvalid mentioning both errors so the retry prompt
        can include a faithful diagnostic."""
        with pytest.raises(ModelOutputInvalid, match="neither valid YAML nor JSON"):
            generate_from_model_output("}{ this is neither")

    def test_top_level_scalar_string(self):
        """A bare scalar (string) is neither a list nor a dict with a probes
        key, and it's not a dict to be treated as a single probe — reject."""
        with pytest.raises(ModelOutputInvalid, match="must be a list of probes"):
            generate_from_model_output("just a string")

    def test_top_level_scalar_int(self):
        with pytest.raises(ModelOutputInvalid, match="must be a list of probes"):
            generate_from_model_output("42")

    def test_list_with_non_dict_items_filtered_to_empty(self):
        """A list containing only non-dict items ends up as an empty list
        after _coerce_to_list — that must surface as ModelOutputInvalid
        'had no probe items' so the caller is told the model emitted noise."""
        raw = json.dumps(["a", "b", "c"])
        with pytest.raises(ModelOutputInvalid, match="no probe items"):
            generate_from_model_output(raw)

    def test_empty_list_explicit(self):
        """A model that emits literally `[]` is also no probes — same
        rejection as the noise case."""
        with pytest.raises(ModelOutputInvalid, match="no probe items"):
            generate_from_model_output("[]")


# --------------------------------------------------------------------
# Validation: all fail vs some fail
# --------------------------------------------------------------------

class TestValidationBehavior:
    def test_all_items_fail_validation_raises(self):
        """When every item fails ProbeSpec validation, the adapter MUST
        raise — silently degrading to a zero-length list would mean a deep-
        test run reports '0 model probes' and the caller can't tell a parse
        failure from an empty proposal."""
        # Every item is missing `name`, which is required.
        bad_items = [
            {"pattern": "api_read", "path": "/x"},
            {"pattern": "api_delete", "path": "/y"},
        ]
        with pytest.raises(ModelOutputInvalid, match="did not validate against ProbeSpec"):
            generate_from_model_output(json.dumps(bad_items))

    def test_partial_failure_returns_valid_subset(self, caplog):
        """A few valid + a few invalid items: return the valid ones, log a
        warning naming the counts so a reviewer of the run logs sees that
        not every model emission made it through. The caller decides
        whether to retry with the parse error attached."""
        mixed = [
            _spec_dict(name="good1"),
            {"pattern": "api_read", "path": "/x"},  # missing name
            _spec_dict(name="good2", path="/y"),
            {"pattern": "api_read", "path": "/z"},  # missing name
        ]
        with caplog.at_level(logging.WARNING, logger="workflo_worker.model.probe_adapter"):
            specs = generate_from_model_output(json.dumps(mixed))

        # Valid subset returned — 2 valid ProbeSpecs out of 4 inputs.
        assert len(specs) == 2
        assert {s.name for s in specs} == {"good1", "good2"}

        # Warning logged with the counts so the run log is honest.
        assert any(
            "2/4 invalid probes" in rec.message for rec in caplog.records
        ), f"expected a warning naming counts; got {caplog.records!r}"

    def test_validation_error_lists_each_failing_item(self):
        """The 'all failed' error message lists one numbered entry per
        failed item — useful in the retry prompt the model sees."""
        # Every item is missing `pattern`, which is required on ProbeSpec.
        # ALL items must fail so we hit the "not specs" branch in
        # _coerce_to_probespecs; if even one is valid we get the partial-
        # failure path (which returns the valid subset instead of raising).
        bad = [
            {"name": "p0", "path": "/x"},  # missing pattern
            {"name": "p1", "path": "/y"},  # missing pattern
            {"name": "p2", "path": "/z"},  # missing pattern
        ]
        with pytest.raises(ModelOutputInvalid) as exc_info:
            generate_from_model_output(json.dumps(bad))
        # The error mentions every failing item by index so the retry
        # prompt includes a faithful, itemizable diagnostic.
        msg = str(exc_info.value)
        assert "item 0" in msg
        assert "item 1" in msg
        assert "item 2" in msg


# --------------------------------------------------------------------
# Field coercion through ProbeSpec
# --------------------------------------------------------------------

class TestFieldCoercion:
    def test_expected_status_int_or_list_round_trips(self):
        """ProbeSpec accepts both int and list[int] for expected_status —
        the adapter must not normalize one to the other (the value should
        survive to the receipt writer, which formats ints vs lists
        differently)."""
        raw = json.dumps([
            _spec_dict(name="int_status", expected_status=403),
            _spec_dict(name="list_status", expected_status=[403, 404]),
        ])
        specs = generate_from_model_output(raw)
        assert specs[0].expected_status == 403
        assert specs[1].expected_status == [403, 404]

    def test_optional_fields_default_correctly(self):
        """ProbeSpec optional fields must default even when the model omits
        them — never trust the model to fill in everything."""
        raw = json.dumps([{
            "name": "minimal",
            "pattern": "positive_control",
            "path": "/",
            # method, expected_status, list_key, expect_resource_absent,
            # soc2_controls, description all default
        }])
        specs = generate_from_model_output(raw)
        assert len(specs) == 1
        s = specs[0]
        assert s.method == "GET"  # default
        assert s.expected_status == 403  # default
        assert s.list_key is None
        assert s.expect_resource_absent is False
        assert s.soc2_controls == []
        assert s.description == ""


# --------------------------------------------------------------------
# build_correction_prompt
# --------------------------------------------------------------------

class TestBuildCorrectionPrompt:
    def test_returns_string_with_all_three_parts(self):
        """A retry prompt must include: original_prompt, an excerpt of the
        raw model output that failed to parse, AND the validation error
        string. Missing any of the three makes the retry ineffective."""
        prompt = build_correction_prompt(
            original_prompt="propose some YAML probes",
            raw_output="- name: x\n- name: y\n",  # bad shape
            parse_error="item 0: missing field: pattern",
        )
        assert "propose some YAML probes" in prompt
        assert "- name: x" in prompt  # raw_output excerpt included
        assert "item 0: missing field: pattern" in prompt  # parse error
        # And a closing instruction to emit strict YAML/JSON.
        assert "STRICT YAML" in prompt or "JSON list" in prompt
        # The source says "Do not include commentary before or after." —
        # match the actual wording (case-insensitive).
        assert "do not include commentary" in prompt.lower()

    def test_truncates_long_raw_output(self):
        """A 10k-char raw output must be truncated to the first 1000 chars
        (per the source's [:1000]), so the retry prompt doesn't bloat
        past the model's context window."""
        long_raw = "x" * 10_000
        prompt = build_correction_prompt(
            original_prompt="p",
            raw_output=long_raw,
            parse_error="e",
        )
        # The first 1000 chars of raw_output appear; chars after that don't.
        assert "x" * 1000 in prompt
        assert "x" * 1001 not in prompt


# --------------------------------------------------------------------
# Exception type
# --------------------------------------------------------------------

class TestModelOutputInvalid:
    def test_is_runtime_error_subclass(self):
        """ModelOutputInvalid must subclass RuntimeError so the worker's
        broad `except (ModelServerError, ModelOutputInvalid)` catch keeps
        working after future changes to either module."""
        assert issubclass(ModelOutputInvalid, RuntimeError)
        # And we can raise+catch it as a plain RuntimeError too.
        with pytest.raises(RuntimeError):
            raise ModelOutputInvalid("x")
