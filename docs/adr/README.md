# Workflo — Architecture Decision Records

Numbering rule: **ADR-001…ADR-014 belong to the Product Engineering Brief v1.0** and are adopted as the project baseline (recorded in `ADR-0001-adopt-brief-decisions.md`). Implementation-level decisions made in this repository continue from **ADR-0015**.

| ADR | Decision | Status |
|---|---|---|
| [0001](ADR-0001-adopt-brief-decisions.md) | Adopt the brief's ADR-001…014 as the frozen architecture baseline | Accepted |
| [0015](ADR-0015-canonical-contracts-home.md) | Canonical contracts live in `packages/workflo-schema` (Python); TS `packages/contracts` is a validated mirror; TS SQL/ledger discipline is adopted | Proposed (pending owner ratification) |
| [0016](ADR-0016-canonical-json-and-evidence-chain.md) | One canonical JSON profile (RFC 8785 subset); integers/strings only in hashed structures; evidence chain v2 forward, legacy v1 formats keep verifying | Proposed |
| [0017](ADR-0017-run-lifecycle-and-outcomes.md) | The brief's 18-state lifecycle is the only product state machine; three independent outcomes (execution / QA verdict / trust) | Proposed |
| [0018](ADR-0018-receipt-v5.md) | Receipt v5: DSSE envelope, validation-before-signing, isolated signer, teardown + ledger-root binding; legacy receipt v1–v4 verification retained | Proposed |
| [0019](ADR-0019-policy-admission.md) | `ExecutionPolicyBundleV1` with 12 frozen components; admission requires a validated, immutable policy digest | Proposed |
| [0020](ADR-0020-event-finding-evidence-contracts.md) | Frozen event registry, four-category finding model with deterministic verification, scoped evidence manifest validation | Proposed |
| [0021](ADR-0021-patch-protocol.md) | Patch proposal/approval binding (exact bytes, base revision, one-time nonce); apply only in a new sandbox | Proposed |
| [0022](ADR-0022-microvm-boundary.md) | Firecracker/KVM microVM per attempt is the only production execution boundary; Docker and bwrap paths are non-production | Accepted (mirrors brief ADR-001/002) |

Status meanings: **Accepted** — in force; **Proposed** — implemented in this pass, awaiting owner ratification before dependent work is treated as stable; **Superseded** — replaced by a later ADR.

How to add one: copy the structure (Context / Decision / Consequences / Alternatives), number sequentially, add to the table above, and reference it from the code it governs.
