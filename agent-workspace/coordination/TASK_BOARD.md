# Workflo multi-agent task board

**Board owner:** project coordinator / human owner. Agents must not modify this global board directly; they submit proposed status changes in their handoff.

**Baseline:** main @ 25e83ec7b3316b630520bbdba8092d0e591cc3de, 2026-11-23. All statuses below are planning statuses pending a fresh CI and workspace run.

## P0 — Baseline and trust blockers

| ID | Task | Owner | Reviewer | Dependencies / acceptance |
|---|---|---|---|---|
| WF-AG-001 | Re-run current per-component baseline; capture test/build/CI evidence | GPT-6 Luna | Gemini | Fresh clean checkout; separate Python suites; TS lint/typecheck/build; record skips and KVM availability |
| WF-AG-002 | Reconcile product boundaries and component dependency graph; identify unmapped paths | Gemini | GPT-6 Luna | Compare PRODUCT_BOUNDARIES, ADRs, package manifests, imports, CI and deployment references |
| WF-AG-003 | Prepare owner decision pack for ADR-0015 through ADR-0021 | Gemini | GPT-6 Luna | No agent may ratify; list conflicts, consequences and dependent work |
| WF-AG-004 | Inventory all inference egress paths and data classes; propose fail-closed freeze | Gemini | GPT-6 Luna + DeepSeek | Read-only inventory first; no provider expansion or route change without owner approval |
| WF-AG-005 | Reconcile receipt writers/readers v1-v5 and identify production/dev signing paths | DeepSeek | GPT-6 Luna + Gemini | Preserve legacy verification; test all writer paths and production dev-key rejection |
| WF-AG-006 | Add explicit runtime profile labels and prove no dev-runtime production fallback | DeepSeek | GPT-6 Luna | Coordinate with canonical schema owner; tests must fail when strict runtime unavailable |

## P1 — Deterministic vertical slice

| ID | Task | Owner | Reviewer | Dependencies / acceptance |
|---|---|---|---|---|
| WF-AG-101 | RunSpec resolved-plan and policy-digest gap closure | DeepSeek | Gemini + GPT-6 | ADR ratification; golden vectors and deterministic digest tests |
| WF-AG-102 | Deterministic source snapshot builder with path/symlink controls | DeepSeek | GPT-6 | Exact commit pinning, stable manifest, hostile path tests |
| WF-AG-103 | Complete guest flow: repo materialization, declared checks and app lifecycle | DeepSeek | GPT-6 | Guest workload bound to RunSpec and snapshot; good/broken FastAPI fixtures |
| WF-AG-104 | Host event spool/evidence completeness and finalizer | DeepSeek | GPT-6 + Gemini | Attempt-bound manifest, tamper/swap/cross-run tests |
| WF-AG-105 | Unify workflo run and run-dev contract without misrepresenting runtime profile | DeepSeek | GPT-6 | Compatibility tests; distinct execution/QA/trust outcomes |
| WF-AG-106 | Prototype-lab reproducible fixture suite | GPT-6 | DeepSeek | Pinned digests; 12 scenarios from implementation blueprint; each fixture has expected result |

## P0 — Firecracker Gate B (real KVM required)

| ID | Task | Owner | Reviewer | Dependencies / acceptance |
|---|---|---|---|---|
| WF-AG-201 | Pin Firecracker/jailer/kernel/rootfs artifacts and digests | MiniMax | DeepSeek + GPT-6 | Reproducible artifact manifest; no mutable image tags |
| WF-AG-202 | Implement actual per-attempt cgroup scope and admission enforcement | DeepSeek | GPT-6 + Gemini | No execution on attach failure; real KVM host evidence |
| WF-AG-203 | Implement enforced per-run egress boundary | DeepSeek | GPT-6 + Gemini | Default deny; DNS rebinding/IP literal/redirect tests; gateway outage fails closed |
| WF-AG-204 | Jailer/seccomp/filesystem and guest-image admission | DeepSeek | GPT-6 + Gemini | Pinned versions, signed image identity and negative tests |
| WF-AG-205 | Guest supervisor, vsock identity and attempt-bound protocol | DeepSeek | Gemini + GPT-6 | No host shell/host filesystem capability; typed protocol and size/sequence limits |
| WF-AG-206 | Teardown inventory, daemon crash recovery and real adversarial Gate B matrix | GPT-6 test owner; DeepSeek fix owner | Gemini | Real KVM boot; no mocks counted as Gate B; retained evidence bundle |

## P2 — Control plane and integrations

| ID | Task | Owner | Reviewer | Dependencies / acceptance |
|---|---|---|---|---|
| WF-AG-301 | Durable dispatch/worker claim integration | MiniMax | DeepSeek + GPT-6 | Transactional outbox, idempotent claim, signed attempt assignment; recovery tests |
| WF-AG-302 | GitHub-first source/CI integration contract | MiniMax | Gemini + GPT-6 | Least-privilege permissions, exact commit pinning, no autonomous merge/deploy |
| WF-AG-303 | CI gate repair and required-check definition | MiniMax | GPT-6 | No continue-on-error around required gates; required security checks block merge |
| WF-AG-304 | npm packaging/install smoke matrix | MiniMax | GLM + GPT-6 | Clean machine, supported OS matrix, package signature/provenance plan |

## P3 — Developer experience, after core stabilization

| ID | Task | Owner | Reviewer | Dependencies / acceptance |
|---|---|---|---|---|
| WF-AG-401 | CLI help/error-message consistency and onboarding docs | GLM | GPT-6 | No duplicate CLI; tests snapshot/help behavior |
| WF-AG-402 | Evidence/receipt documentation and examples | GLM | Gemini + GPT-6 | Match actual schema, no unsupported security claims |
| WF-AG-403 | Dashboard UX improvements | GLM | Gemini + GPT-6 | Only after evidence workflow is stable; API contract exists |
| WF-AG-404 | Developer quickstart and troubleshooting refresh | GLM | GPT-6 | Validate commands on clean checkout; clearly mark platform constraints |

## Status discipline

- BACKLOG: not ready to start.
- READY: dependencies, scope, owner, paths and test criteria are explicit.
- IN_PROGRESS: branch/worktree and base SHA recorded.
- BLOCKED: exact blocker and evidence recorded.
- IMPLEMENTED_UNVERIFIED: code and handoff exist; review/gates not complete.
- VERIFIED: independent review and mandatory tests pass.
- ACCEPTED: human approved the change.

No row is marked complete based on this planning commit. Reconcile every item with the latest repository and actual CI before starting.
