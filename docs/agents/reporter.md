# Reporter

**Purpose:** readable, trustworthy output. **Why:** engineers act on reports only if the facts are checkable.

**Input:** Findings, RunSummary, isolation proof, requirement statuses. **Output:** ReportBundle (JSON + HTML).

## How
1. Build the structured report from data: counts, statuses, severities, evidence links, requirement statuses (verified, failing, uncovered, inconclusive), isolation proof (backend, canary, teardown).
2. For each of the top findings, the LLM (if enabled) fills only `explanation`, `likely_cause_hypothesis` (always labeled hypothesis) and `remediation_hint`.
3. Validator: cited evidence ids must be a subset of the finding's evidence; numbers and ids in the text must exist in the data; no new facts. On failure use the plain template for that finding.
4. Render HTML and JSON by code, never by the model.
5. Always include provider provenance and model_stage_degraded.

## Acceptance tests
LLM disabled still produces a complete report; a draft citing an unknown evidence id is rejected; a hypothesis is never rendered as a confirmed cause; report states which provider and privacy mode handled each call.
