# Five-Agent Operating Model — Ownership, Permissions, Integration and Daily Control

**Applies to:** M1 25-day delivery and post-M1 work  
**Integrator:** human product owner / explicitly delegated integration lead  
**Primary rule:** one owner per deliverable, one canonical interface, independent review for sensitive work.

## 1. Authority hierarchy

1. **Human product owner:** scope, architecture ratification, budget, security exceptions, branch protection, merge and release decision.
2. **Accepted ADRs:** binding architecture constraints.
3. **M1 plan and interface registry:** milestone sequence, semantic contract, ownership and acceptance.
4. **OpenAPI and canonical schema:** exact wire/client contract once approved.
5. **Agent runbook:** task-level implementation instructions.
6. **CI/evidence:** proof of behavior; never authority to weaken architecture.

Models do not act as equal co-owners or final decision-makers. An agent may propose a design, but it cannot approve its own canonical/security change.

## 2. Workstream RACI

| Deliverable | Responsible | Accountable | Consult/review |
|---|---|---|---|
| Go CLI core/API client/verifier | DeepSeek | Human owner | GLM, Luna, MiniMax |
| CLI commands/output/GitHub SHA connector | GLM | Human owner | DeepSeek, Luna, MiniMax |
| FastAPI/OpenAPI/admission/runner APIs | GPT-6 Luna | Human owner | DeepSeek, GLM, MiniMax |
| Existing Firecracker host adapter integration | DeepSeek | Human owner | Luna, MiniMax |
| Threat model/security test suite | MiniMax | Human security owner | DeepSeek, Luna |
| Dashboard IA/design prep | Gemini | Human product owner | Luna, GLM |
| Canonical schema/receipt/protocol change | Proposal by relevant owner | Human owner | All affected agents |
| Final M1 acceptance | Evidence submitted by all | Human owner | Independent security review |

## 3. Explicit ownership and non-overlap

- DeepSeek owns `apps/workflo-cli-go/cmd/workflo/`, `internal/core/`, `internal/api/`, `internal/auth/`, `internal/verify/`, `internal/runnerclient/` and the reserved M1 host adapter integration.
- GLM owns `apps/workflo-cli-go/internal/commands/`, `internal/connectors/github/`, `internal/clioutput/`, `internal/profiles/` and CLI golden fixtures. DeepSeek publishes the interfaces first.
- MiniMax owns threat-model documents, synthetic adversarial fixtures, security/privacy test suites and security findings. It may propose pure policy code only after path/interface reservation.
- Luna owns `apps/control-plane/` M1 route/service/model/migration/test changes, the OpenAPI source/snapshot and PostgreSQL integration fixtures.
- Gemini owns dashboard design documents and synthetic prototypes before M1; `apps/dashboard/` production implementation only after M1 acceptance.
- The Python Firecracker host under `worker/` remains the M1 execution reference. DeepSeek owns narrow adapter integration; do not create a parallel Firecracker manager.
- `packages/workflo-schema/`, receipt format, lifecycle enums, runner assignment, guest protocol, policy defaults and signing/trust semantics are shared protected surfaces. One writer at a time and human approval before mutation.

File boundaries are detailed in the runbooks. If the real repository structure differs, agent must report the observed path and request an ownership adjustment; do not create duplicate directories to match a guessed plan.

## 4. Stage gates for every task

### G0 — Ready
A task has ID, outcome, owner, allowed files, no-touch list, interface version, dependencies, test command, acceptance and reviewer.

### G1 — Audit
Read current source/tests and report reuse points. No broad rewrite before the gap map is accepted.

### G2 — Interface
Agree producer/consumer semantics and generate fixtures before implementing both sides. Canonical schema, receipt, lifecycle and security policy changes require human approval.

### G3 — Implement
Small PR; one meaningful vertical behavior at a time; test in the same PR; preserve backward compatibility.

### G4 — Independent review
Another owner checks behavior, changed-file scope, tests, compatibility and security. Security/identity/tenant/crypto changes require human review.

### G5 — Integrate
Rebase on current main, run relevant tests in canonical checkout, validate cross-agent contract and attach evidence.

### G6 — Accept
Record explicit PASS/BLOCKED/WAIVED with evidence. A PR merge is not milestone acceptance.

## 5. Agent permission tiers

| Tier | Permission | Conditions |
|---|---|---|
| **T0** | Read-only audit | Default for all agents |
| **T1** | Documentation and synthetic tests | Task scope, paths and test target are clear |
| **T2** | Bounded implementation | Calibration pass, frozen interface, reserved paths, reviewer and acceptance checks |
| **T3** | Sensitive implementation | Explicit human authorization per task; mandatory human review after implementation |

T3 areas include Firecracker/jailer invocation, Linux capabilities, cgroups/network policy, credentials, tenant/RLS, crypto, receipt signing, trust classification and release security. No model gets broad T3 permission.

**Never granted by default:** production secrets, production deployment, destructive production DB action, org administration, production shell/SSH, authority to remove gates, sign official release or make final security claims.

Calibration has not been run unless the evidence ledger contains real platform/model IDs, run metadata, a diff and independently reproduced test results. A plan, public benchmark or assistant assertion does not grant T2.

## 6. Calibration gate

Before T2, each model must:
- run common audit, seeded bug/regression, contract mismatch and CI diagnosis tasks;
- complete its specialization task from the same recorded baseline;
- obey allowed/forbidden paths;
- pass all hard disqualifiers;
- score at or above owner-approved threshold;
- receive two independent reviewers; one human for security, identity, tenant, crypto and privacy.

If external model runner/credentials are unavailable, keep all model coding at T1 and have a human integrator execute the critical path. Do not fabricate model runs. The owner may grant a temporary narrow T2 task only after recording an explicit calibration exception and reviewer controls.

## 7. Daily M1 cadence (IST)

- **09:30:** report previous day evidence, today's single primary outcome, dependencies and shared-file reservations.
- **13:00:** 15-minute cross-agent integration check; resolve only blockers/interface conflicts.
- **18:30:** PR-ready checkpoint; run target tests and attach outputs.
- **20:00:** integrator reviews/merges compatible PRs, rebases dependent branches and updates next-day critical path.

No blocker may remain unreported for more than one working day. KVM, signing key, GitHub installation, API schema or local worktree access blockers are escalated immediately.

## 8. Required agent daily report

```text
Agent/model:
Task IDs:
Base SHA:
Branch/worktree:
Commit SHA:
Outcome delivered:
Files changed:
Contract/interface version:
Exact test commands:
Passed / failed / skipped:
Environment class: UNIT | MOCKED-INTEGRATION | LOCAL-INTEGRATION | REAL-KVM | OFFLINE-VERIFICATION
Artifacts/evidence paths and SHA-256:
Security/privacy impact:
Known limitations:
Blocked by:
Next deliverable and expected reviewer:
PR URL:
```

A status update without exact commands and test counts is incomplete.

## 9. PR requirements

Every PR must include:
- task IDs and owner;
- reason and scope;
- changed-file inventory;
- API/schema/protocol impact;
- tests added and exact commands/results;
- environment class, including mocked vs real;
- security/privacy assessment;
- rollback/compatibility note;
- known limitations and remaining work;
- UX screenshots or browser evidence where relevant.

No agent self-merges or self-approves. A PR that changes a protected interface needs affected consumers and owner approval.

## 10. Branch/worktree discipline

- Each agent works only in its assigned worktree and branch.
- Worktrees must be created from the same accepted main after the planning PR is merged.
- Never force-reset a worktree with uncommitted changes.
- A branch must be rebased on current main daily where safe; conflicts are resolved by the file owner.
- Only one agent writes a reserved shared file at a time.
- The integration lead owns cherry-pick/rebase sequencing and records merged SHA.
- Local worktrees are not considered created until verified on the developer machine.

## 11. Integration sequence

1. Freeze OpenAPI, RunSpec and assignment semantics.
2. DeepSeek publishes CLI core/client interfaces.
3. GLM implements handlers/connectors against those interfaces.
4. Luna publishes API routes and generated fixtures against same contract.
5. DeepSeek connects strict dispatch to existing Firecracker host adapter.
6. MiniMax runs independent tests at each boundary.
7. DeepSeek integrates evidence, teardown and offline verification.
8. Gemini starts production dashboard only after signed M1 acceptance.

Daily small merges are preferred to a large end-of-milestone merge.

## 12. Escalation triggers

Stop and ask for a decision when:
- accepted ADR conflicts with requested implementation;
- producer/consumer contract mismatch is found;
- KVM/Firecracker artifact or trust anchor is unavailable;
- GitHub source access would expose a credential to guest;
- a model requests broader host/network/tool privilege;
- a change would alter V1 receipts, lifecycle or tenant isolation;
- Windows/macOS strict local execution is being implied;
- zero-budget assumption is violated;
- a security test is unrun or unknown but someone proposes marking it green.

## 13. Definition of done

Task accepted only with reproducible evidence and reviewer approval. M1 accepted only under the separate M1-25-DAY-EXECUTION-PLAN and milestone evidence record; no PR count or calendar date substitutes.
