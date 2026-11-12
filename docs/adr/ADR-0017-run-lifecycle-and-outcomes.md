# ADR-0017 — Run lifecycle and outcome model

**Status:** Proposed · 2026-11-11

## Context

Four incompatible lifecycle representations exist today: API `RunStatus` (5 values), the namespace runtime's `STAGE_ORDER` (12 internal stages), the TS rebuild's 9-state DB graph, and the brief's state machine (18 states). The brief also mandates split outcomes: execution status, QA verdict, and trust status are independent (tests may pass while teardown fails; a reproducible defect is `completed/fail`).

## Decision

1. **The brief's state machine is the only product lifecycle**, frozen verbatim from the baseline diagram:

   `CREATED → ADMITTED → PROVISIONING → SOURCE_ACQUISITION → PREPARING → EXECUTING → EVALUATING → COLLECTING_EVIDENCE → TEARDOWN → VERIFYING_TEARDOWN → SIGNING → COMPLETED`
   with failure terminals `INFRASTRUCTURE_FAILED` (from PROVISIONING), `EXECUTION_FAILED` (from SOURCE_ACQUISITION/PREPARING/EXECUTING), `TEARDOWN_FAILED` (from VERIFYING_TEARDOWN), `ATTESTATION_FAILED` (from SIGNING), `REJECTED` (from ADMITTED), and `CANCEL_REQUESTED` (from PROVISIONING/SOURCE_ACQUISITION/PREPARING/EXECUTING) leading to `TEARDOWN`.

2. **Transitions have authorities.** Each legal transition is owned by exactly one authority: `admission` (control plane), `orchestrator`, or `user` (cancellation request). A guest component can never advance the product state; guest messages are observations until the orchestrator validates and applies the transition.

3. **Cancellation is a request.** `CANCEL_REQUESTED` is reachable only from the four active states drawn in the baseline; from there the run always proceeds through `TEARDOWN` and `VERIFYING_TEARDOWN`. A cancelled run still terminates at `SIGNING → COMPLETED` when teardown verifies — cancellation is recorded in the outcome (`cancelled: true`), not by a separate terminal state. *Open question recorded:* pre-provisioning cancellation (from `CREATED`/`ADMITTED`) has no edge in the frozen diagram; it is intentionally **not** added without an owner decision.

4. **Three independent outcomes are stored and reported separately:**

   | Outcome | Values |
   |---|---|
   | Execution status | `completed`, `rejected`, `infrastructure_failed`, `execution_failed`, `teardown_failed`, `attestation_failed` (+ `cancelled: bool`) — mapped 1:1 from the terminal state |
   | QA verdict | `pass`, `fail`, `warn`, `inconclusive`, `not_applicable` |
   | Trust status | `verified_clean`, `verification_failed`, `cleanup_incomplete`, `unknown`, decomposed into evidence-validation, teardown-verification, and receipt components |

5. **"Clean success" is defined, not implied:** execution `completed`, not cancelled, trust `verified_clean` with all three components verified (`is_clean_success`). A stricter predicate `is_full_pass` additionally requires `qa_verdict == pass`; any user-facing "checks passed" claim must use `is_full_pass`, while "the run itself is trustworthy" uses `is_clean_success`.

6. **API status is derived** from the lifecycle state; the internal stage order (snapshot/deps/rootfs/app/agent/…) remains a guest-side implementation detail reported as events, never as product state.

## Consequences

- `workflo_schema.contracts.lifecycle` / `outcomes` implement the frozen machine, `can_transition()`, `required_authority()`, terminal sets, and `is_clean_success()`.
- The TS DB transition graph and the control-plane API must be migrated to this machine (Phase 2 / Gate A); until then the legacy API states remain a compatibility surface only.
- `docs/locked-manifests.md`'s `RunStateSchema` (9 states) is superseded for product state and remains only as a legacy note.

## Alternatives considered

- Extending the TS 9-state machine: fewer states than the brief's reporting needs (no separate teardown verification, signing, cancellation).
- Keeping API `RunStatus` as the product machine: cannot express the trust/execution split the brief requires.
