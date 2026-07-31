from typing import List, Dict
from app.models.future import FutureScenario


def _score(candidate: FutureScenario, objective: str, constraints: Dict) -> float:
    risk_weight = 0.5
    effort_weight = 0.2
    benefit_weight = 0.3

    if objective == "minimize incident risk":
        risk_weight = 0.6
        effort_weight = 0.15
        benefit_weight = 0.25
    elif objective == "minimize effort":
        risk_weight = 0.25
        effort_weight = 0.55
        benefit_weight = 0.20
    elif objective == "maximize reliability":
        risk_weight = 0.55
        effort_weight = 0.20
        benefit_weight = 0.25
    elif objective == "balance cost and risk":
        risk_weight = 0.35
        effort_weight = 0.35
        benefit_weight = 0.30

    constraint_penalty = 0.0
    max_effort = constraints.get("max_effort")
    if max_effort is not None and candidate.predicted_effort > max_effort:
        constraint_penalty = 20.0

    score = (
        benefit_weight * candidate.predicted_benefit
        - risk_weight * candidate.predicted_severity
        - effort_weight * candidate.predicted_effort
        + 10 * candidate.confidence
        - constraint_penalty
    )

    return score


def rank_candidates(
    candidates: List[FutureScenario],
    objective: str = "minimize incident risk",
    constraints: Dict = None
) -> FutureScenario:
    if not candidates:
        raise ValueError("No candidates to rank")

    constraints = constraints or {}

    max_effort = constraints.get("max_effort")
    if max_effort is not None:
        filtered = [c for c in candidates if c.predicted_effort <= max_effort]
        if filtered:
            candidates = filtered

    return max(candidates, key=lambda c: _score(c, objective, constraints))