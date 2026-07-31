from typing import List
from app.models.future import FutureScenario


def build_explanation(ranked_choice: FutureScenario, candidates: List[FutureScenario]) -> List[str]:
    explanation = []

    explanation.append(f"Selected: {ranked_choice.scenario_type}")
    explanation.append(f"Predicted severity: {ranked_choice.predicted_severity}/100")
    explanation.append(f"Predicted effort: {ranked_choice.predicted_effort}/100")
    explanation.append(f"Predicted benefit: {ranked_choice.predicted_benefit}/100")
    explanation.append(f"Confidence: {ranked_choice.confidence:.0%}")

    if candidates:
        sorted_by_severity = sorted(candidates, key=lambda c: c.predicted_severity)
        sorted_by_benefit = sorted(candidates, key=lambda c: c.predicted_benefit, reverse=True)
        sorted_by_effort = sorted(candidates, key=lambda c: c.predicted_effort)

        best_low_risk = sorted_by_severity[0]
        best_high_benefit = sorted_by_benefit[0]
        lowest_effort = sorted_by_effort[0]

        if ranked_choice.future_id == best_low_risk.future_id:
            explanation.append("This is the lowest-risk option among all candidates.")

        if ranked_choice.future_id == best_high_benefit.future_id:
            explanation.append("This option provides the highest predicted benefit.")

        if ranked_choice.future_id == lowest_effort.future_id:
            explanation.append("This option requires the least engineering effort.")

        if ranked_choice != best_low_risk and ranked_choice.predicted_severity <= best_low_risk.predicted_severity + 15:
            explanation.append(
                f"Slightly higher risk than the safest option ({best_low_risk.scenario_type}), "
                f"but offers better benefit/effort tradeoff."
            )

    if ranked_choice.evidence:
        explanation.append("Evidence from impact analysis:")
        for item in ranked_choice.evidence[:3]:
            explanation.append(f"  - {item}")

    return explanation