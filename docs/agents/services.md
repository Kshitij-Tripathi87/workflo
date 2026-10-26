# Deterministic services

## Orchestrator
State machine: INIT, SNAPSHOT, SANDBOX_READY, ANALYZE, EXPLORE_BASELINE, JUDGE, EXPLORE_LLM, JUDGE, REPORT, TEARDOWN, DONE. Illegal transitions rejected. Validates each handoff against its contract. Enforces budgets and timeouts. Writes every transition to the Postgres event log. Maps failures to exit codes via failure_stage. Teardown always runs.

## ToolGateway (security-critical)
The only path from a model to the app. Deny by default.
- Targets: the SandboxHandle app URL only. No redirects off-host, no other hosts, no file or non-HTTP schemes, no link-local or metadata addresses.
- Methods and paths: configurable allowlist; default safe methods plus explicit POST on listed paths.
- Budgets: max calls, per-call timeout, response size cap, total time.
- Redaction: secrets and tokens stripped from stored requests and responses.
- Every call logged by hash with a verdict (allowed or denied and why). Denials are counted and reported.

## Evidence ledger / Notary (security-critical)
sha256 manifest of every artifact, hash-chained entries. Findings may reference only manifest ids. `workflo verify` re-hashes and fails (exit 4) on any mismatch. Existing receipts are reused as-is; signature work is post-beta.

## Sandbox backend
Docker by default (build stage with egress, sealed run stage with none), namespaces optional on Linux. Backend-scoped probe profiles. Receipts derive runtime_type, backend version and image digest from the backend that ran. Labeled resources, teardown verified by query.

## ModelProvider
OpenAI-compatible client, self-hosted first then hosted fallback, health check, timeouts, one repair attempt, provider and privacy mode on every call, ModelCallRecord with prompt hash only. Privacy modes: local-only, hybrid, observation-only (default until a self-hosted endpoint exists).
