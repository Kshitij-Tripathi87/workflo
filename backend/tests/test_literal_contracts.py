"""Literal-vocabulary contracts for the engine <-> model boundary.

These pin defects that the CI false-green hid: ``mypy app/`` was run as
``mypy ... || true``, so argument-type errors against pydantic ``Literal``
fields were reported but never failed the build. Two of them were live crashes:

1. ``FutureScenario.scenario_type`` was missing "assign_owner", so
   ``generate_futures()`` raised ValidationError for any asset with no owner -
   the product's flagship scenario.
2. ``_tool_write_back`` passed LLM-supplied free-form strings straight into
   Literal-typed models, so an unexpected action type from the model aborted the
   whole autopilot task.

The invariant tests below fail if the vocabularies drift apart again.
"""

from typing import get_args

import pytest
from app.engine.future_search_engine import _build_candidates, generate_futures
from app.models.asset import AssetNode, GraphSnapshot
from app.models.future import ScenarioType as FutureScenarioType
from app.models.recommendation import RecommendationAction
from app.models.scenario import ScenarioType as AppScenarioType


def _snapshot(*, kind: str, owner: str | None) -> GraphSnapshot:
    node = AssetNode(
        urn="urn:test:asset",
        name="asset",
        kind=kind,
        owner=owner,
        schema_fields=["col_a"],
    )
    return GraphSnapshot(nodes={node.urn: node}, edges=[])


@pytest.mark.parametrize(
    "kind", ["dataset", "pipeline", "dashboard", "model", "feature"]
)
@pytest.mark.parametrize("owner", [None, "data-platform"])
def test_every_candidate_matches_the_model_vocabularies(kind, owner):
    """Every (scenario_type, action_label) pair must be a legal Literal value."""
    scenario_vocab = get_args(AppScenarioType)
    action_vocab = get_args(FutureScenarioType)

    candidates = _build_candidates(_snapshot(kind=kind, owner=owner), "urn:test:asset")
    assert candidates, "expected at least one candidate"

    for scenario_type, action_label, _change, _effort in candidates:
        assert scenario_type in scenario_vocab, scenario_type
        assert action_label in action_vocab, action_label


def test_generate_futures_for_ownerless_asset_does_not_raise():
    """Regression: ownerless assets used to crash FutureScenario validation."""
    plan = generate_futures(_snapshot(kind="dataset", owner=None), "urn:test:asset")

    assert plan.candidates
    assert all(
        c.scenario_type in get_args(FutureScenarioType) for c in plan.candidates
    )


def test_every_proposed_action_is_a_known_action():
    """Proposed actions must be in the action vocabulary, and - except for the
    deliberate no-op baseline - must also be recommendable."""
    proposed = {
        label
        for _scenario, label, _change, _effort in _build_candidates(
            _snapshot(kind="dataset", owner=None), "urn:test:asset"
        )
    }

    assert proposed <= set(get_args(FutureScenarioType))
    # "do_nothing" is the baseline candidate: it is a legal future state but
    # deliberately not a Recommendation (you don't recommend inaction).
    assert proposed - {"do_nothing"} <= set(get_args(RecommendationAction))


def test_write_back_normalises_untrusted_llm_strings():
    """Unknown severity/action from the LLM must not raise mid-run."""
    from app.services.agent import CortexAgent

    agent = CortexAgent.__new__(CortexAgent)  # no LLM/context store needed

    record = agent._tool_write_back(
        asset_urn="urn:test:asset",
        severity="catastrophic",  # not in the vocabulary
        action_type="do_something_weird",  # not in the vocabulary
        summary="llm proposed an unknown action",
        confidence=0.5,
    )

    assert record["asset_urn"] == "urn:test:asset"
