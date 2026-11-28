# Workflo beta execution board — v2 CLI-first

**Board owner:** human owner / project coordinator  
**Baseline:** main at 373b02918a87854efe4427b1f4e4ae79905457e8 (2026-11-28)  
**Status:** proposed backlog. None of these tasks is complete by being listed here.

## Rules

Every task uses the task contract. Re-run the baseline and current CI at the immutable task base. Reconcile this backlog against current source before assigning. The old blueprint status counts are not current proof. No fixed-date delivery plan; gates determine release.

## P0 — Repository, trust baseline and owner decisions

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-001 | Fresh full test/build/CI baseline | GPT-6 Luna | Gemini | Per-component results, exact SHA, pass/fail/skip/not-run counts, KVM availability and false-green audit |
| WF2-002 | Active/legacy/unresolved path and dependency map | Gemini | GPT-6 Luna | Imports, package manifests, entry points, CI, install scripts and deployment references |
| WF2-003 | Reconcile ADR-0015 to ADR-0023 | Gemini | GPT-6 + human | Decision pack; preserve Proposed status pending owner decisions |
| WF2-004 | Rust-vs-Go proof criteria and CLI spike | DeepSeek | Gemini + GPT-6 | Cross-platform proof, measured comparison limits and owner decision |
| WF2-005 | Existing Python CLI parity inventory | DeepSeek | GPT-6 | Commands, flags, output, exit codes, config, callers and install compatibility |
| WF2-006 | Source/secret/hosted-prompt data-flow map | Gemini | GPT-6 + DeepSeek | Data classes, all egress paths, typed allowlist and negative canary plan |
| WF2-007 | API/tenant/RLS current-state inventory | GPT-6 Luna | Gemini | FastAPI routes, DB ownership, membership and authorization gaps |

## P1 — Native CLI foundation (G1)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-101 | Rust workspace and CLI skeleton | DeepSeek | GPT-6 | help/version/doctor, config, stable errors/JSON and CI targets for three OSes |
| WF2-102 | Config schema and init workflow | DeepSeek | GLM + GPT-6 | Versioned schema, safe defaults, validation and secret-free config |
| WF2-103 | Native binary build matrix | MiniMax | DeepSeek + GPT-6 | Linux/macOS/Windows artifacts, checksums and clean-machine smoke |
| WF2-104 | npm/pnpm/Bun wrapper proof | MiniMax | GPT-6 | Three package managers select and verify correct native binary |
| WF2-105 | CLI journey and installation guide | GLM | GPT-6 | Commands reproduced on clean machines; supported/unsupported modes explicit |

## P2 — CLI run vertical slice (G2)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-201 | Canonical RunSpec and protocol golden vectors | GPT-6 contract / DeepSeek adapter in separate tasks | Gemini | Approved schema, versioning and byte/field compatible Python/Rust vectors |
| WF2-202 | Source inspect and deterministic snapshot | DeepSeek | GPT-6 | Exact commit, path/symlink checks, deterministic digest and no source upload |
| WF2-203 | Development run adapter and Python compatibility | DeepSeek | GPT-6 | End-to-end dev run, dry-run, explicit profile, receipt verifier compatibility |
| WF2-204 | Receipt writer/reader v1-v5 reconciliation | DeepSeek | GPT-6 + Gemini | Legacy verification retained; no ambiguous current-version claims |
| WF2-205 | Cross-language profile fixture set | GPT-6 | DeepSeek | Good/broken/timeout/missing-toolchain/path/permissions/evidence fixtures |

## P3 — Customer-controlled runner / Firecracker Gate B (G3)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-301 | Runner identity, enrollment, lease and assignment contract | GPT-6 | Gemini | Short-lived credential, signed attempt-bound assignment and replay policy |
| WF2-302 | Native runner lifecycle client | DeepSeek | GPT-6 | register/status/heartbeat/drain/reconnect and revoked-runner tests |
| WF2-303 | Host checkout and guest source materialization | DeepSeek | GPT-6 | Full SHA, host-only Git credential and guest-bound snapshot proof |
| WF2-304 | Cgroup/jailer/egress/image-admission gaps | DeepSeek on narrow security tasks | GPT-6 + Gemini + human | Real KVM enforcement, fail-closed admission and adversarial tests |
| WF2-305 | Teardown/crash recovery and Gate B matrix | GPT-6 test owner; DeepSeek fix owner | Gemini + human | Real VM evidence, inventory, teardown and recovery proof; mocks excluded |

## P4 — Four language profiles and three gates (G4)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-401 | Python/FastAPI profile | DeepSeek | GPT-6 | Pinned image, core/deep/security fixture matrix |
| WF2-402 | Node/Express profile | DeepSeek | GPT-6 | npm/pnpm/Bun declared commands, startup and test matrix |
| WF2-403 | Go profile | DeepSeek | GPT-6 | go test/vet/build and bounded deep/security fixtures |
| WF2-404 | Java/Spring profile | DeepSeek | GPT-6 | Maven/Gradle/JUnit and bounded deep/security fixtures |
| WF2-405 | Independent gate status and aggregation | GPT-6 | Gemini | PASS/FAIL/BLOCKED/SKIPPED/NOT_REQUESTED/ERROR semantics |
| WF2-406 | Bounded deep AI test loop and evaluations | GPT-6 | Gemini + DeepSeek | Tool/time/output budgets, reproducible findings and labeled evaluation set |
| WF2-407 | Security adversarial matrix | GPT-6 | Gemini + human | Sandbox/privacy/tenant/evidence negatives with real KVM requirements identified |

## P5 — GitHub, private repositories and PR checks (G5)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-501 | GitHub App permission/webhook design | MiniMax | GPT-6 + Gemini | Least privilege, token lifetime, signature and replay model |
| WF2-502 | Private source checkout | MiniMax | DeepSeek + GPT-6 | Short-lived token, full SHA, no token in guest, cleanup |
| WF2-503 | Core/Deep/Security PR check runs | MiniMax | GPT-6 | Correct independent statuses and idempotent rerun |
| WF2-504 | Webhook replay/retry test suite | MiniMax | GPT-6 | Forgery/replay rejection and duplicate-delivery idempotency |

## P6 — API and individual/team identity contracts (design in parallel)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-601 | OpenAPI route and compatibility contract | GPT-6 | Gemini | Versioned API, request IDs, errors, pagination and idempotency |
| WF2-602 | Individual/org membership and role matrix | GPT-6 | Gemini | Action-level permissions, invitation, revoke and role-change semantics |
| WF2-603 | RLS and cross-tenant negative suite | GPT-6 | Gemini + human | PostgreSQL-based cross-tenant tests covering all resource types |
| WF2-604 | GitHub source/check-run API integration contract | MiniMax | GPT-6 | Provider identity, source connection and PR check schemas |
| WF2-605 | Existing FastAPI control-plane implementation tranche | GPT-6 | Gemini + DeepSeek | Approved contract only, migration rollback and all contract tests |

## P7 — Capacity, distribution and release (G6/G8/G9)

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-701 | 15-user × 3-run load test | GPT-6 | MiniMax | 45 durable submissions, backpressure, fairness, isolation and restart recovery |
| WF2-702 | Binary checksum/SBOM/provenance pipeline | MiniMax | GPT-6 | Source SHA, builder identity, digest, SBOM and provenance artifacts |
| WF2-703 | Install/update/uninstall cross-platform tests | MiniMax | GLM + GPT-6 | Linux/macOS/Windows and npm/pnpm/Bun/native matrices |
| WF2-704 | Fresh-machine release acceptance and rollback | GPT-6 | Gemini + human | Gate evidence pack, honest known limits and go/no-go recommendation |

## P8 — Dashboard after CLI/API gates

| ID | Task | Owner | Reviewer | Exit evidence |
|---|---|---|---|---|
| WF2-801 | Dashboard IA and static prototype | GLM | Gemini | Page-to-API map and correct gate/trust terminology |
| WF2-802 | Workspace/project/run/gate/evidence screens | GLM | GPT-6 | Role-aware UI, API contract tests, accessibility and responsive build |
| WF2-803 | Runner/audit views | GLM | GPT-6 | No secret/source disclosure and permission tests |

## Stop conditions

Mark BLOCKED and stop if an owner ADR is unresolved; a path is outside allowlist; real KVM is unavailable for a strict gate; a mandatory test is skipped/masked; privacy/data-flow boundary is unclear; tenant test fails; implementation relies on benchmark scores instead of acceptance evidence; or a task requires Workflo-funded infrastructure outside the zero-budget decision.
