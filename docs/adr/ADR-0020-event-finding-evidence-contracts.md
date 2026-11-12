# ADR-0020 — Event, finding, and evidence contracts

**Status:** Proposed · 2026-11-11

## Context

Events, findings, and evidence exist in three partial shapes: the Python runtime's JSONL ledger + `Finding` (evidence-ref authority rule) + `EvidenceBinding`; the TS `PublicAgentEventSchema` (strict, no-CoT, 8 roles × 20 kinds) + `JudgeDecisionSchema` + `evidence_events` table; the brief's payload-digest event model and four-category finding taxonomy. The brief requires one canonical contract, a strict no-chain-of-thought rule, guest events as observations only, and evidence that rejects cross-run/cross-tenant references.

## Decision

1. **Canonical event contract (`RunEventV1`)**: `event_id`, organization/project/run/attempt identity (+ sandbox when applicable), `sequence_number` (per attempt, ≥1), `event_type` from a **frozen registry** (40 canonical types covering lifecycle, sandbox, source, tests, probes, agent action propose/validate/deny/execute, observations, findings, evidence bundle, teardown, receipt, cancellation, run completion), `occurred_at` (canonical ms string), `producer` identity `{component, role?, instance_id, version}`, `correlation_id`, `payload_digest`, and a strict payload (no floats; unknown keys rejected; **no chain-of-thought fields** — `thought`, `reasoning`, `internal`, `chain`, `cot` are rejected by name).

2. **Producer trust classes**: components are classified `trusted-control` (control plane, orchestrator, host worker, evidence service, signer), `trusted-guest` (guest supervisor, QA runtime, agent runtime, tool gateway — observations), and `user`. Only trusted-control producers can drive lifecycle transitions; guest events are recorded as observations and validated by the trusted side before any state consequence.

3. **Canonical finding model (`FindingV1`)**: stable id; scope (org/project/run/attempt); `source_revision`; title; `category ∈ {verified_failure, candidate, inconclusive, infrastructure_failure, not_tested}`; severity; expected/observed behavior; optional reproduction reference; `evidence_refs`; detector identity + version; optional model provenance (candidate-stage only); uncertainty; `verified_by` stamp (`verifier` identity + `criteria_id`) — **required for `verified_failure` and forbidden to be a model component**: a model can produce candidates, only deterministic verification can produce verified failures. `infrastructure_failure` findings never count as product defects, and `not_tested` is a scope record, never a defect claim.

4. **Evidence contract (`EvidenceArtifactV1` + `EvidenceManifestV1`)**: each artifact binds tenant/run/attempt/sandbox scope, type, media type, size, sha256, producer identity, producing stage/action, source/policy/runtime digests, classification, retention policy, validation state (`received | validated | rejected | superseded`), and an opaque immutable object reference. The manifest aggregates artifacts for exactly one attempt, plus the ledger root/count/chain version. **Cross-run and cross-tenant references are rejected** by an explicit scope validator (`assert_scoped`), and corrections supersede — they never mutate finalized evidence.

5. **No hidden chain-of-thought** anywhere in the API/UI: event payloads and findings carry concise rationale and observable facts only (inherited from the locked no-CoT rule).

## Consequences

- `workflo_schema.contracts.{events,findings,evidence}` implement the above with strict models and scope validators.
- The TS `PublicAgentEventSchema`/`JudgeDecisionSchema` become UI-legacy and are superseded for new events; the mapping is documented in the mirror package.
- The evidence service (Phase 5/6) consumes `EvidenceManifestV1`; the receipt binds its digest.

## Alternatives considered

- Keeping three formats and translating: rejected — translation layers become the de-facto authority and break cross-verification.
