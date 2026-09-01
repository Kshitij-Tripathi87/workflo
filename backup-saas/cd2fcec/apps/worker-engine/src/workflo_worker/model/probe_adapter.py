"""probe_adapter — validate + parse model output into ProbeSpec list.

The model server returns a free-form string. We don't trust it as schema-
valid ProbeSpec YAML/JSON, even though it's a code-instruct model — LLMs
are unreliable at strict structured output, and a malformed emission
must not crash ProbeGenerator or silently produce garbage probes.

This module provides:
    generate_from_model_output(raw: str) -> list[ProbeSpec]

    Validate-then-construct: yaml.safe_load (or json.loads) -> ProbeSpec(**item)
    Pydantic's own validation rejects bad shapes (missing required fields,
    wrong types, etc.) before they reach ProbeGenerator.

    The caller (worker engine) is responsible for retry semantics:
        for attempt in range(2):
            try:
                specs = generate_from_model_output(model.generate(...))
                break
            except ModelOutputInvalid:
                # re-prompt with the parse error appended
                ...
        else:
            # explicit failure with model_inference_error set; do NOT silently
            # fall back to surface probes — that would misrepresent what tier
            # of testing actually ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml  # PyYAML is a dep of probe-engine already

from probe_engine.models import ProbeConfig, ProbeSpec


class ModelOutputInvalid(RuntimeError):
    """Raised when the model's raw output cannot be parsed into ProbeSpecs.

    Catching this is the signal to retry with a corrected prompt.
    """


def _parse_yaml_or_json(raw: str) -> Any:
    """Try YAML first (more permissive), fall back to strict JSON.

    YAML is the default because model output tends to include commentary
    that breaks strict JSON parsers but parses cleanly as YAML. JSON
    parsing is attempted second because, for models that DO emit strict
    JSON, it's a faster path.

    Returns the parsed structure, or None if YAML/JSON parsed to nothing
    (e.g. an empty string sneaked past the empty check, or a YAML stream
    that's only whitespace/comments). Raises ModelOutputInvalid only if
    BOTH parsers fail.
    """
    yaml_err: Optional[Exception] = None
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        yaml_err = e
    else:
        # YAML parsed cleanly. `parsed` may be None for an empty/comment-only
        # stream — that's not a parse error; the caller decides whether to
        # reject "None" as invalid model output.
        return parsed

    # We only reach here if YAML raised. Try strict JSON next.
    try:
        return json.loads(raw)
    except json.JSONDecodeError as json_err:
        raise ModelOutputInvalid(
            f"Model output is neither valid YAML nor JSON. "
            f"YAML error: {yaml_err}. JSON error: {json_err}."
        ) from json_err


def _coerce_to_list(parsed: Any) -> list[dict]:
    """The model might return either a top-level list of probe dicts
    OR a dict containing a `probes` key with a list. Both are valid;
    we normalize to list[dict].
    """
    if isinstance(parsed, list):
        # Top-level list — already in the right shape.
        return [p for p in parsed if isinstance(p, dict)]

    if isinstance(parsed, dict):
        # Try the ProbeConfig shape: {"probes": [...]}
        if "probes" in parsed and isinstance(parsed["probes"], list):
            return [p for p in parsed["probes"] if isinstance(p, dict)]

        # Sometimes the model wraps the list under a different key.
        # Try the most common alternatives.
        for key in ("probe_specs", "tests", "specs"):
            if key in parsed and isinstance(parsed[key], list):
                return [p for p in parsed[key] if isinstance(p, dict)]

        # Otherwise treat the dict itself as a single probe.
        return [parsed]

    raise ModelOutputInvalid(
        f"Model output must be a list of probes or a dict with a "
        f"'probes'/'probe_specs'/'tests'/'specs' key. Got {type(parsed).__name__}."
    )


def _coerce_to_probespecs(items: list[dict]) -> list[ProbeSpec]:
    """Validate each dict via ProbeSpec(**item). Pydantic raises
    ValidationError on missing fields or wrong types — we translate
    that into ModelOutputInvalid so the caller can retry with a
    corrected prompt.
    """
    from pydantic import ValidationError

    specs: list[ProbeSpec] = []
    errors: list[str] = []

    for i, item in enumerate(items):
        try:
            specs.append(ProbeSpec(**item))
        except ValidationError as e:
            errors.append(f"item {i}: {e}")

    if errors and not specs:
        # All items failed — let the caller retry.
        raise ModelOutputInvalid(
            "Model output did not validate against ProbeSpec:\n" + "\n".join(errors)
        )

    if errors:
        # Partial failure — accept the valid ones but record the failures.
        # This is a softer error than "all failed": the model got SOME
        # of the shape right. We return the valid ones and let the caller
        # decide whether to retry the whole thing.
        import logging
        logging.getLogger(__name__).warning(
            "Model output had %d/%d invalid probes; accepting %d valid ones",
            len(errors), len(items), len(specs),
        )

    return specs


def generate_from_model_output(raw: str) -> list[ProbeSpec]:
    """Parse raw model output into a list of validated ProbeSpecs.

    Raises ModelOutputInvalid on any failure. The caller decides retry
    policy — this function is intentionally pure (no I/O, no model
    calls) so it's trivially testable and reusable.
    """
    if not raw or not raw.strip():
        raise ModelOutputInvalid("Model output was empty")

    parsed = _parse_yaml_or_json(raw)
    if parsed is None:
        raise ModelOutputInvalid("Model output parsed to None (empty YAML stream)")

    items = _coerce_to_list(parsed)
    if not items:
        raise ModelOutputInvalid("Model output had no probe items")

    return _coerce_to_probespecs(items)


def build_correction_prompt(
    original_prompt: str,
    raw_output: str,
    parse_error: str,
) -> str:
    """Build a follow-up prompt that asks the model to fix its bad output.

    Used by the worker engine to retry once on parse failure — append the
    parse error to the original prompt and ask the model to emit corrected
    output. We bound the retry to ONE attempt (per the plan: "one retry on
    parse failure, then fail the deep-test stage explicitly").
    """
    return (
        f"{original_prompt}\n\n"
        f"---\n"
        f"Your previous response did not validate. Here is what you returned:\n"
        f"```\n{raw_output[:1000]}\n```\n\n"
        f"Validation error:\n{parse_error}\n\n"
        f"Please retry, emitting a STRICT YAML list (or JSON list) of probe "
        f"specs matching the schema. Do not include commentary before or after."
    )


__all__ = [
    "ModelOutputInvalid",
    "generate_from_model_output",
    "build_correction_prompt",
]
