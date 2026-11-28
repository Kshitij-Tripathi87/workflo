# Workflo Agent Workspace — CLI-First Enterprise Delivery Programme

**Planning baseline:** 28 November 2026  
**Release model:** quality-gated technical beta; no calendar-driven production cutover  
**Repository:** Kshitij-Tripathi87/workflo  
**Development agents:** Gemini 4 Hydrogen, MiniMax M3.1 Flash, DeepSeek V4.1 Flash-1017, GLM-5.3 Flash, GPT-6 Luna

This is the single source of truth for assigning the five development models to Workflo engineering. These models are used to build Workflo itself. They are **not** Workflo customer-facing inference providers and must never be inserted into the product's customer inference configuration.

## 1. Owner decisions captured

The plan incorporates the following approved discovery answers:

| Decision | Selected direction |
|---|---|
| Initial load | 10–15 concurrent users, each able to submit multiple runs |
| Execution placement | Both customer-controlled and future hosted; customer-controlled is the default |
| CLI/runtime implementation | Native Rust or Go; this plan recommends Go |
| Client OS | Linux, macOS and Windows |
| Initial language ecosystems | Python, Node.js, Go and Java |
| Customer inference | Customer BYOK APIs; hosted prompts are metadata-only and require explicit consent |
| Test capabilities | Core, deep AI-assisted and security testing, with separate gates |
| Source integration | GitHub, including private repositories and PR checks |
| Web schedule | API contracts and design now; substantial web implementation after CLI/sandbox acceptance |
| Identity | Individual developers and organization/team workspaces |
| Infrastructure budget | Zero Workflo infrastructure budget; customer-owned compute and BYOK |
| Release date | No fixed deadline; launch only after all required quality/security gates |

Any change to these decisions requires an explicit owner decision and a recorded ADR or plan revision.

## 2. Product definition

Workflo verifies software changes against an exact repository revision and declared policy. It executes approved checks in a controlled environment, records bounded evidence, independently verifies teardown and creates an independently verifiable signed receipt.

Its outputs keep three questions separate:

1. **Execution:** did the run complete correctly as an infrastructure operation?
2. **QA:** what did the checks establish about the software?
3. **Trust:** was the execution/evidence/teardown process verified?

A verified test failure can be a valid QA finding. A passing test with incomplete teardown is not a trustworthy successful run.

## 3. The launch workflow

The first complete product workflow must be:

1. Install the native Workflo CLI.
2. Run workflo --help and get discoverable commands and examples.
3. Authenticate as an individual or select an organization/workspace.
4. Initialize or select a project.
5. Connect GitHub or use a local repository.
6. Resolve an exact full commit SHA and a versioned run policy.
7. Run workflo doctor and determine whether the machine is an eligible strict runner or a client that must use a remote customer-owned runner.
8. Submit a run with an idempotency key.
9. Admit it through the control plane and assign it to an eligible customer runner.
10. Provision a fresh Firecracker/KVM microVM for the attempt.
11. Acquire the exact source snapshot and prepare dependencies in a separately constrained preparation stage.
12. Execute core tests, deep AI-assisted checks and security checks as separately authorized stages.
13. Collect evidence and classify execution, QA and trust outcomes separately.
14. Independently verify teardown.
15. Sign a receipt only after the relevant trust checks pass.
16. Verify the receipt locally/offline.
17. Publish a GitHub commit/PR check only when the installation has the required narrowly scoped permission.
18. Later, present the same actual run, timeline and evidence through the web app.

The first release must make this flow reliable before expanding to more integrations or autonomous write actions.

## 4. Model assignment: three CLI agents, two web/platform agents

This replaces the older assignment in the previous planning pack.

| Agent | Primary ownership | Why this fit |
|---|---|---|
| **DeepSeek V4.1 Flash-1017** | Native Go CLI core, runner agent and execution runtime integration | Strongest reported DeepSWE v1.1 and Terminal-Bench 4.0 results in this exact five-model group |
| **GLM-5.3 Flash** | CLI command experience, GitHub/local connectors, language profiles and npm/package distribution | Strong reported Toolathlon Verified and Terminal-Bench 2.1 results; suitable for multi-tool workflows |
| **MiniMax M3.1 Flash** | Sandbox policy, security engineering, adversarial test automation and inference/privacy boundary tests | Highest reported Automation-Bench v1.0.6 result in this model set and a strong reported CyberGym score |
| **Gemini 4 Hydrogen** | Web application UX, frontend implementation and browser-based product validation | Google explicitly lists web development and agentic workflows; strong published automation and computer-use results |
| **GPT-6 Luna** | Control-plane/backend architecture, API contracts, tenancy, persistence, auth and web backend | Published long-horizon software-engineering performance with strong cost-efficiency; suitable for sustained backend integration |

The full numbers, benchmark versions, harnesses, limitations and sources are in [Model benchmark and routing analysis](MODEL-BENCHMARK-ROUTING.md). The assignments are priors, not guarantees. Every model must pass Workflo-specific calibration tasks before being trusted with high-impact implementation.

## 5. Critical architecture choice: Go for the native CLI/runtime

**Recommendation: use Go, not a mixed Go/Rust rewrite.**

Reasons:

- Produces native executables for Linux, macOS and Windows from one codebase.
- Simple release matrix and cross-compilation.
- Strong standard library for HTTP, TLS, processes, filesystem and concurrency.
- Faster migration path for the current team than a simultaneous Rust rewrite.
- Mature CLI, testing, profiling and packaging ecosystem.
- Garbage-collected memory-safe language by default; OS/KVM/Firecracker controls—not language choice—remain the primary sandbox boundary.

Go is recommended for:
- the native workflo CLI;
- customer runner daemon/agent;
- host-side Firecracker lifecycle control and protocol client;
- shared Go protocol/policy bindings generated from canonical schemas where appropriate.

Do **not** rewrite every existing Python test adapter, framework plugin or guest test engine at once. Preserve the existing Python execution path as a compatibility/reference implementation while the Go CLI and runner are delivered in vertical slices. Migrate a component only after contract parity and real integration evidence. No big-bang rewrite and no second parallel production sandbox.

## 6. Strict platform truth

Cross-platform **CLI installation** is not the same as cross-platform strict **sandbox execution**.

| Platform | CLI client | Strict local runner | Launch behavior |
|---|---|---|---|
| Linux x86_64 with KVM | Yes | Yes, only after Gate B passes | Primary customer-owned strict runner |
| Linux ARM64 with KVM | Yes | Conditional on tested Firecracker/guest artifacts | Enable only after hardware/architecture acceptance |
| macOS Apple Silicon/Intel | Yes | Not Firecracker/KVM under the current ADR | CLI connects to customer-owned Linux KVM runner; local dev mode must be labelled non-strict |
| Windows x64 | Yes | Not Firecracker/KVM under the current ADR | CLI connects to customer-owned Linux KVM runner; WSL2/dev mode is not strict production isolation |
| Windows ARM64 | Conditional | No launch claim | Support only after the binary and integration matrix passes |

Do not promise strict local execution on macOS or Windows merely because the binary installs there. Do not call Docker, WSL2 or bubblewrap equivalent to the approved Firecracker boundary. If local strict execution on these platforms is later required, create a separate architecture/security ADR for the native hypervisor and prove its boundary independently.

## 7. Customer-owned and hosted execution

- **Launch default:** customer-controlled Linux/KVM runner, enrolled to the Workflo control plane using short-lived identity.
- **Hosted architecture:** define the runner abstraction and API contract now, but do not operate a Workflo-funded fleet under the zero-budget constraint.
- **Future hosted offering:** enable only when infrastructure funding, isolation operations, monitoring, incident response and cost model exist.
- Customer compute is customer-funded. BYOK provider usage is customer-funded.
- The product must expose where a run executed and which runtime profile was used.

## 8. Multi-user and scale target

The product must be designed for 10–15 concurrent authenticated users, each submitting multiple runs.

The control plane must safely handle bursts without losing or duplicating run intent. The initial load-test scenario is 15 concurrent user sessions, each submitting 3 run requests in a short burst (45 submissions). This is an admission/queueing scenario, **not** a promise to execute 45 microVMs simultaneously.

Execution concurrency is capacity-based:
- runners advertise CPU, memory, disk and supported profile capacity;
- admission reserves capacity before provisioning;
- organization/project/user quotas bound noisy tenants;
- fair scheduling prevents one organization monopolizing a runner;
- excess work queues with visible state and cancellation;
- no fixed concurrency number is advertised before measured runner benchmarks.

## 9. Work sequence

### Phase 0 — Architecture and calibration
- Freeze product boundaries and protocol versions.
- Create the Go architecture proposal and decide the migration seam.
- Audit existing CLI, npm shim, Python host, worker, schemas, FastAPI control plane and Next.js shell.
- Run a same-repository benchmark calibration across all five agents.
- Prepare threat model, API contract and UI journeys.

### Phase 1 — Native CLI and connector foundation
- Build the Go workflo binary and stable command tree.
- Add auth/config, doctor, init, project selection, source resolution and run submission.
- Build GitHub App workflow and local repository connector.
- Replace Python-dependent npm installation with signed native binary packages.
- Keep old Python CLI available for parity comparisons; do not publish a misleading package.

### Phase 2 — Runner and sandbox
- Complete the Go runner/host lifecycle behind the existing typed assignment contract.
- Complete Firecracker/KVM boot, resource/network isolation, guest protocol and independent teardown.
- Build reproducible guest images and four language profiles.
- Prove run lifecycle end-to-end with deterministic tests.

### Phase 3 — Deep AI and security
- Build BYOK provider boundary with explicit per-run consent and allowlisted metadata.
- Block direct source-bearing hosted calls.
- Add structured planner and governed ToolGateway.
- Add core/deep/security stage gates and adversarial tests.
- Enable AI only after real privacy/model acceptance passes.

### Phase 4 — Web application
- Implement the dashboard after CLI and runner contracts stabilize.
- Reuse the same APIs and outcome contracts as the CLI.
- Implement projects, runs, runner management, evidence/receipt, settings, integrations, teams and audit.
- Prove tenant and role isolation.

### Phase 5 — Beta acceptance
- Cross-platform install test.
- 15-user/45-submission burst test.
- KVM Gate B.
- Four-language test matrix.
- GitHub private repo/PR-check flow.
- Inference privacy/BYOK gate.
- Tenant/RLS/runner recovery/chaos gate.
- Signed release provenance and SBOM.
- Clean-machine end-to-end pilot.

## 10. Agent runbooks

- [DeepSeek — native CLI and runner runtime](agents/01-deepseek-native-cli-runner.md)
- [GLM — CLI experience, connectors and distribution](agents/02-glm-cli-connectors-distribution.md)
- [MiniMax — sandbox security and adversarial QA](agents/03-minimax-sandbox-security-qa.md)
- [Gemini — web application frontend and UX](agents/04-gemini-web-frontend.md)
- [GPT-6 Luna — backend, API and platform architecture](agents/05-gpt6-luna-backend-platform.md)

Shared execution documents:
- [Product architecture](PRODUCT-ARCHITECTURE.md)
- [Workspace and repository restructuring](REPOSITORY-STRUCTURE.md)
- [CLI product specification](CLI-PRODUCT-SPEC.md)
- [API and web contract plan](API-WEB-CONTRACTS.md)
- [Quality, security and release acceptance](QUALITY-RELEASE-GATES.md)
- [Agent operating model](AGENT-OPERATING-MODEL.md)

## 11. Non-negotiable engineering rules

1. No source code reaches a hosted provider through the metadata-only inference profile.
2. BYOK does not mean a provider is authorized to receive source code.
3. No direct model call may bypass the approved privacy gateway in strict mode.
4. No shell/tool action is authorized solely because an LLM asked for it.
5. Firecracker/KVM is the only strict production execution boundary until a new ADR is accepted and proven.
6. No strict-to-development fallback.
7. No guest access to host shell, Docker socket, credentials or host filesystem.
8. No receipt claims verified trust without independent teardown/evidence verification.
9. No tenant or organization scope is trusted from client-supplied IDs alone.
10. No feature is done because an agent says it is done; acceptance tests and review must pass.
11. No coding agent merges to main, deploys production or changes production secrets.
12. The five development models are not customer inference providers.

## 12. Definition of release-ready

A clean supported client installation can authenticate, connect a GitHub private repository or local repository, pin a full SHA, submit a policy-bound run, route it to an eligible customer-owned Linux/KVM runner, execute the requested core/deep/security profiles inside a fresh Firecracker microVM, collect evidence, verify teardown independently, produce a signed receipt, verify it offline and expose the same result through the web API/dashboard.

Any capability without real evidence remains disabled or labelled experimental. The owner makes the final release decision.

## 13. Documents and navigation

### Architecture and shared contracts
- [Model benchmark and task routing](MODEL-BENCHMARK-ROUTING.md)
- [Product architecture](PRODUCT-ARCHITECTURE.md)
- [Repository restructuring and worktrees](REPOSITORY-STRUCTURE.md)
- [CLI product specification](CLI-PRODUCT-SPEC.md)
- [API and web contract plan](API-WEB-CONTRACTS.md)

### Delivery and governance
- [Dependency-driven delivery roadmap](DELIVERY-ROADMAP.md)
- [Quality, security and release gates](QUALITY-RELEASE-GATES.md)
- [Agent operating model](AGENT-OPERATING-MODEL.md)
- [Workflo-specific model calibration protocol](MODEL-CALIBRATION-PROTOCOL.md)

### Five agent runbooks
- [DeepSeek — native Go CLI and runner](agents/01-deepseek-native-cli-runner.md)
- [GLM — CLI commands, connectors and distribution](agents/02-glm-cli-connectors-distribution.md)
- [MiniMax — sandbox policy, security and adversarial QA](agents/03-minimax-sandbox-security-qa.md)
- [Gemini — web frontend and UX](agents/04-gemini-web-frontend.md)
- [GPT-6 Luna — control plane and backend](agents/05-gpt6-luna-backend-platform.md)

## 14. Active agent branches

- agent/deepseek-native-cli-runner
- agent/glm-cli-connectors-distribution
- agent/minimax-sandbox-security-qa
- agent/gemini-dashboard-frontend
- agent/gpt6-luna-backend-platform

The agent branches are initialized from this plan. The integrator must merge/rebase the accepted planning PR before implementation PRs target main, or rebase each implementation branch on the updated main. Do not start implementation from the superseded branch names listed in REPOSITORY-STRUCTURE.md.
## API and dashboard preparation

- [M1 control-plane API contract audit and freeze proposal](API-CONTRACT-FREEZE-M1.md)
- [Dashboard design-system preparation brief](DASHBOARD-DESIGN-SYSTEM-PREPARATION.md)

## First execution milestone

- [Milestone 1 — Native CLI → Firecracker/KVM → independently verified receipt](MILESTONE-01-NATIVE-CLI-FIRECRACKER-RECEIPT.md)
- [Model calibration result ledger](model-calibration-results.md)
- Accepted Go language decision: [ADR-0024](../adr/ADR-0024-native-go-cli-and-runner.md)
- Local agent worktree bootstrap: [Bash](../../scripts/dev/bootstrap-agent-worktrees.sh) · [PowerShell](../../scripts/dev/bootstrap-agent-worktrees.ps1)
