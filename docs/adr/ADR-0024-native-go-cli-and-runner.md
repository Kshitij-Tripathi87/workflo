# ADR-0024 — Native Go CLI and incremental Go customer-runner migration

**Status:** Accepted — owner decision · 2026-11-28  
**Scope:** Native CLI, customer runner implementation language and staged migration

## Context

Workflo currently has a Python CLI at `apps/workflo-cli/`, a Python Firecracker/KVM host foundation under `worker/`, a Python guest engine at `apps/worker-engine/`, a FastAPI control plane at `apps/control-plane/`, and an npm wrapper that creates a Python virtual environment and installs vendored wheels. The repository has no Go modules on the current main baseline.

The product requires a native `workflo` client for Linux, macOS and Windows, plus a customer-controlled execution runner. Strict production execution remains Linux/KVM-only under ADR-0022. The control plane and guest adapters are not required to share the CLI's implementation language.

The programme has a zero-infrastructure budget and must preserve existing receipt, policy, lifecycle and assignment compatibility. A big-bang rewrite would multiply risk before the first real microVM workflow is proven.

## Decision

1. **Go is the implementation language for the new native CLI.** The primary executable is `workflo`. It must not require a Python runtime, package-local virtual environment, Node runtime or model runtime to execute.
2. **Go is the target language for the customer-runner host agent, introduced incrementally.** The current Python host under `worker/` remains the behavioral and integration reference until the Go path passes contract parity, real KVM Gate B and end-to-end receipt verification.
3. **The control plane remains FastAPI/Python for this programme.** Do not rewrite it in Go solely for language uniformity. Backend changes remain in `apps/control-plane/` and consume the approved contracts.
4. **The guest execution engine and language adapters remain fit-for-purpose.** Python/Node/Go/Java guest tooling may coexist. The runner language does not dictate guest language.
5. **The strict production boundary does not change.** One fresh Firecracker/KVM microVM per run attempt remains mandatory under ADR-0022. Go code is not an isolation boundary. Docker, bwrap, namespaces alone, and a native process runner are not fallback production modes.
6. **The CLI is cross-platform; strict execution is not.** Release the CLI for supported Linux, macOS and Windows client targets only after clean-install and behavior tests. The strict customer runner initially targets eligible Linux x86_64 KVM hosts; other architectures require explicit real-host acceptance. macOS and Windows clients connect to a customer-owned eligible Linux runner.
7. **Prefer CGO-free CLI builds.** Use `CGO_ENABLED=0` where dependencies allow; verify the final binary's actual dynamic-library requirements, reproducibility, signatures and provenance. Do not describe a build as static without inspecting the produced artifact.
8. **Migrate beside, not over, the existing implementation.** Add `apps/workflo-cli-go/`, `apps/workflo-runner-go/`, and generated/validated Go protocol bindings as needed. Do not move or delete the Python CLI, `worker/`, guest engine, or canonical schema package until the relevant compatibility and release gates pass.
9. **Canonical contracts remain unchanged by language migration.** Python `packages/workflo-schema/` remains the initial source of truth. Go types are generated or validated mirrors. Any changes to receipt, lifecycle, assignment, guest/host protocol, policy or evidence semantics require a separate approved decision.
10. **No premature dashboard implementation.** API/OpenAPI contract work and frontend design preparation may proceed, but substantial dashboard implementation remains blocked until the native CLI → real Firecracker → independently verified receipt milestone passes.
11. **The first vertical slice is narrow and deterministic.** Given a full Git commit SHA, an authorized customer runner must acquire exactly that revision, create a fresh verified microVM, execute one pinned deterministic test profile, collect bounded evidence, independently verify teardown, produce the signed receipt and pass offline verification. No model/provider is required for this core slice.

## Rationale

- Go offers a practical balance of single-binary distribution, cross-platform build support, a mature standard library for CLI/network/process work, and a lower migration burden for a small team.
- Rust offers stronger compile-time memory-safety guarantees and a strong systems ecosystem, but would add a second systems-language learning and integration surface during a programme already migrating the CLI and runner.
- Python remains appropriate for the existing FastAPI backend, schemas and guest adapters; there is no product benefit in rewriting stable components solely to achieve one-language uniformity.
- The relevant security boundary is enforced by Linux/KVM, Firecracker/jailer, kernel configuration, cgroups, seccomp, network policy, a narrow typed host API, immutable artifacts and independent teardown evidence. The language is secondary to those controls.

## Consequences and constraints

- Go CLI work can begin after the task-specific Workflo calibration and interface freeze; the first executable must be useful before broad command parity is attempted.
- The first native CLI slice must expose a stable command/error/JSON contract and a typed API client. Connector and package managers integrate through explicit interfaces rather than forking the CLI entrypoint.
- Runner migration must preserve V1 compatibility and introduce new protocol versions explicitly. A Go implementation must pass the same real KVM fixture matrix as the current Python host.
- No Go runner release may claim strict isolation based on unit tests, mocks, Docker, bwrap, or CI without KVM.
- Worktree ownership and shared-file reservations in `docs/agent-workspace/AGENT-OPERATING-MODEL.md` are binding during parallel implementation.

## Alternatives considered

- **Rust for both CLI and runner:** technically viable; deferred in favor of Go's lower integration and team adoption cost. Revisit only with measured evidence that Go blocks a required capability or creates a material security defect.
- **Keep Python CLI and package its venv:** rejected because it preserves a multi-runtime install and operational dependency, and does not meet the native CLI product requirement.
- **Rewrite the control plane in Go:** rejected because it adds risk without advancing the first trusted execution milestone.
- **Run tests directly on the host or use Docker/bwrap as production fallback:** rejected by ADR-0022.
- **Replace all Python components at once:** rejected because it destroys the current behavioral reference and makes regressions difficult to isolate.

## Review triggers

Revisit only if:
- the Go CLI cannot satisfy the supported OS/architecture install matrix;
- a measured Go runtime limitation prevents a required host function;
- a reproducible security defect is attributable to the implementation language/runtime;
- canonical contract or Firecracker architecture changes under a separately reviewed ADR.
