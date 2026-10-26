# Product crew overview

Roles: Analyst -> Explorer -> Judge -> Reporter, driven by a deterministic Orchestrator. Services: ToolGateway, Evidence ledger (Notary), Sandbox backend. Fixer is post-beta.

## Run timeline (who, when)
1. SNAPSHOT (host, deterministic): clone, pin commit, hash snapshot.
2. SANDBOX_READY: build phase (egress allowed), sealed run phase, canary stored as evidence.
3. ANALYZE: Analyst -> ProjectMap, RequirementSet.
4. EXPLORE_BASELINE: Explorer deterministic probes -> Candidates.
5. JUDGE: every Candidate reproduced twice plus control -> Findings.
6. EXPLORE_LLM (optional, budgeted): proposals via ToolGateway -> Candidates -> JUDGE again.
7. REPORT: Reporter -> ReportBundle (JSON + HTML).
8. TEARDOWN: sweep by label, verify absence, seal manifest and receipt.

## Why this shape
- Trust is concentrated in two deterministic places: the Judge (what is real) and the ToolGateway (what a model may touch).
- LLM stages are additive. Remove them and the product still works.
- Every handoff is a validated contract, so a bad model output fails one stage, not the run's integrity.

## Default budgets (tune after the benchmark)
Run 15 min; Analyst LLM <= 3 calls; Explorer LLM <= 20 gateway calls and 5 min; Reporter <= 1 call per finding, top 10 findings.

## Degrade rules
No model endpoint, timeouts, or malformed output after one repair attempt: skip the LLM stage, continue deterministically, set model_stage_degraded in the report. Exit 3 for the agent stage only when deep-test was explicitly required and no fallback worked.
