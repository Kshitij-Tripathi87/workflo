# ADR-0019 — Execution policy bundle and admission

**Status:** Proposed · 2026-11-11

## Context

No admission layer exists today: the token `ADMITTED` appears nowhere in the tree; `POST /v1/runs` validates a spec but no immutable execution policy governs the run; the sandbox assignment carries limits but no signed policy digest. The brief requires "policy before execution" (ADR-005), a versioned `ExecutionPolicyBundle` with 12 components, and admission to reject any run whose policy is invalid — before provisioning.

## Decision

1. **`ExecutionPolicyBundleV1`** is the admission artifact: bundle id, version, organization, creator, `effective_from`, and exactly twelve components, each with its own version, schema version, authority, payload, and a **verified digest** (`sha256:` over the component's canonical payload; the digest stored on the component must equal its recomputation — enforced by validator).

   Components (each versioned independently): `source`, `runtime`, `resource`, `command`, `filesystem`, `network`, `agent_capability`, `model`, `artifact`, `evidence`, `retention`, `teardown`.

2. **Admission sequence** (implemented in Phase 1/2):
   validate caller authorization → resolve run spec → resolve profile to a full bundle → validate bundle (schema, digest recomputation, component completeness, organization scope, no agent-editable fields) → persist the bundle immutably + record `policy_digest` on the run → transition `CREATED → ADMITTED`. Any failure transitions to `REJECTED` (or refuses to create the run), never to execution.

3. **The bundle is immutable per run.** Changing any policy input creates a new bundle version; an admitted run's digest never changes. The `policy_digest` appears in the run contract and the receipt v5 payload.

4. **Agents and users cannot widen policy mid-run.** The agent runtime reads the admitted bundle; any agent-proposed action outside it is denied (tool gateway). Policy management requires an explicit authority (`policy:manage`), distinct from run creation.

## Consequences

- `workflo_schema.contracts.policy` implements the bundle with completeness + digest verification.
- The control plane gains a policy service + admission endpoint behavior in Phase 2; the existing `RunRequest` validation becomes a pre-check, not the admission decision.
- Every sandbox assignment (see ADR-0022) carries the `policy_digest`; the worker refuses mismatched assignments.

## Alternatives considered

- Per-component ad-hoc limits without a bundle: cannot produce one auditable policy digest, cannot gate admission atomically.
