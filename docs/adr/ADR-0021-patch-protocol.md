# ADR-0021 — Patch proposal and approval binding

**Status:** Proposed · 2026-11-11

## Context

No remediation capability exists in the tree yet. The brief requires an immutable proposal, pre-review validation of model-generated diffs, explicit human approval bound to exact bytes, application in a **new** sandbox, retest, and (only if separately authorized and implemented later) remote write-back. "If the complete approval/apply/retest protocol is not ready, ship evidence-backed findings and suggestions only; defer apply."

## Decision

1. **`PatchProposalV1` binds**: proposal id; org/project; originating run/attempt; finding id; **exact base commit and base snapshot digest**; target ref; `patch_digest` (sha256 over the exact patch bytes); normalized unified diff (size-capped); `allowed_files` (safe relative paths only); generator identity (component + optional model provenance); pre-review validation record; state; creation/expiry timestamps.

2. **Patch state machine** (frozen):
   `PROPOSED → VALIDATING → READY_FOR_REVIEW → APPROVED | REJECTED`; `APPROVED → APPLYING_IN_SANDBOX → PATCH_APPLIED_IN_SANDBOX → VERIFYING → VERIFIED | REGRESSION | INCONCLUSIVE`. Terminal: `REJECTED`, `VERIFIED`, `REGRESSION`, `INCONCLUSIVE`, `EXPIRED`, `REVOKED`. An approval is **one-shot** (consumed at apply); expired/stale/revoked/consumed proposals cannot transition.

3. **Pre-review validation rules** (structural, in the contract module): parse a unified diff; reject absolute paths, `..` traversal, drive letters, backslashes, symlink-target escape patterns, disallowed roots, too many files, oversized diffs, binary/generated-file markers, and secret-shaped additions. Model-provided paths are untrusted input.

4. **`PatchApprovalV1` binds** proposal id + proposal digest, patch digest, base commit, base snapshot digest, target ref, allowed-paths digest, approver identity, authorization version, timestamp, and a **one-time nonce**. `approval_matches(proposal, approval)` is a pure function; any byte/base/path change invalidates the approval. Authorization is re-checked at apply time.

5. **Application and verification always use a new sandbox** (ADR-012), acquire the exact base revision, apply the exact approved bytes in the guest, and run reproduction + targeted + regression + build checks, producing a resulting-tree digest and a new receipt. The customer checkout and remote branches are never mutated implicitly.

## Consequences

- `workflo_schema.contracts.patch` implements the models, the state machine, the path-safety validator, and the approval-binding function with tests.
- The review UI, apply orchestrator, and remote write-back are Phase 7; until they exist, Workflo ships **suggestions only** — the contract makes that the enforced default (`state` cannot leave `READY_FOR_REVIEW` without an approval record).

## Alternatives considered

- Free-form approval ("approve this PR"): cannot bind exact bytes, replaying or swapping diffs would be undetectable.
