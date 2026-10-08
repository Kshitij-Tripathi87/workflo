"""Policy evaluation engine — turn advisory into enforcement.

The policy engine sits on top of the simulation engine. It takes a
FuturePlan (with predicted severity + blast radius) and a list of
declared policies and returns a verdict: pass, warn, or block.

This is what lets Cortex move from "reporting impact" to "enforcing
governance" — the difference between an advisory tool and infrastructure.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


Verdict = Literal["pass", "warn", "block"]


class Policy(BaseModel):
    """A declarative rule evaluated against a FuturePlan.

    Examples (cortex.yml):
        policies:
          - name: Prevent High-Risk Deployments
            max_severity: 75
            max_blast_radius: 10
            action: block

          - name: Require Owner on Gold Assets
            require_owner: true
            action: warn

          - name: Warn on Criticality
            action: require_approval
    """

    model_config = {"extra": "forbid"}

    name: str = "default"
    max_severity: Optional[float] = None
    max_blast_radius: Optional[int] = None
    require_owner: bool = False
    action: Verdict = "block"


class PolicyResult(BaseModel):
    """Result of evaluating one policy against one plan."""

    policy_name: str
    verdict: Verdict
    reason: str
    trigger_values: dict = Field(default_factory=dict)


def evaluate_policies(
    policies: list[Policy],
    severity: float,
    blast_radius: int,
    has_owner: bool,
) -> list[PolicyResult]:
    """Evaluate each declared policy against the plan's metrics.

    Returns a list of PolicyResult for every policy that was VIOLATED.
    Policies that pass without violation are not included — silence = OK.
    """
    results: list[PolicyResult] = []

    for policy in policies:
        violations: list[str] = []

        if (
            policy.max_severity is not None
            and severity > policy.max_severity
        ):
            violations.append(
                f"severity {severity} exceeds max {policy.max_severity}"
            )

        if (
            policy.max_blast_radius is not None
            and blast_radius > policy.max_blast_radius
        ):
            violations.append(
                f"blast radius {blast_radius} exceeds max {policy.max_blast_radius}"
            )

        if policy.require_owner and not has_owner:
            violations.append("asset has no assigned owner")

        if violations:
            results.append(
                PolicyResult(
                    policy_name=policy.name,
                    verdict=policy.action,
                    reason="; ".join(violations),
                    trigger_values={
                        "severity": severity,
                        "blast_radius": blast_radius,
                        "has_owner": has_owner,
                    },
                )
            )

    return results


def combine_verdict(results: list[PolicyResult]) -> Verdict:
    """Combine multiple policy results into a single verdict.

    Block dominates Warn, Warn dominates Pass. If no policies were
    violated, the verdict is pass.
    """
    if not results:
        return "pass"

    verdicts = {r.verdict for r in results}
    if "block" in verdicts:
        return "block"
    if "warn" in verdicts:
        return "warn"
    return "pass"


def policies_from_dicts(policy_dicts: list[dict]) -> list[Policy]:
    """Build a list of Policy objects from raw dicts (e.g. loaded from YAML)."""
    policies: list[Policy] = []
    for d in policy_dicts or []:
        try:
            policies.append(Policy(**d))
        except Exception:
            continue
    return policies
