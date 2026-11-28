# Workflo Delivery Roadmap — Dependency-Driven, No Fixed Launch Date

## 1. Release posture

No calendar deadline overrides the quality gates. Deliver the CLI and runner first. Design API contracts and dashboard UX in parallel, but defer substantial web application implementation until the CLI vertical slice is accepted.

## 2. Phase map

### Phase 0 — Workspace, audits and decisions

Owners: all five agents; GPT-6 consolidates system map; human owner ratifies architecture.

Exit:
- exact main SHA recorded;
- all five specialization tasks calibrated;
- Go CLI/runtime ADR approved;
- current CLI/npm/Python worker migration map accepted;
- CLI command tree and run contract frozen;
- runner assignment protocol frozen;
- source, network and BYOK threat models accepted;
- OpenAPI baseline and web screen map approved;
- separate Git worktrees ready.

### Phase 1 — Native CLI foundation

Owners: DeepSeek core, GLM command handlers, MiniMax policy tests.

Deliver:
- workflo Go binary;
- help/version/completion;
- config and credential-store interfaces;
- doctor and strict/dev eligibility output;
- init and project selection;
- auth client and workspace context;
- dry-run plan;
- typed API client;
- JSON output and stable error taxonomy;
- Go unit/contract tests;
- CI cross-compilation.

Exit:
- Linux/macOS/Windows client builds run help/version/doctor without Python;
- no API/receipt contract drift;
- local and remote command behavior is documented.

### Phase 2 — Connectors and install distribution

Owners: GLM, with DeepSeek core interface and GPT-6 GitHub server API.

Deliver:
- local source connector;
- GitHub App install/repository picker;
- private repo scope and token expiry behavior;
- exact commit resolution;
- source manifest and size/symlink/submodule policies;
- npm/pnpm/Bun packages with platform binaries;
- native macOS/Windows/Linux archives;
- checksum/provenance and upgrade/rollback.

Exit:
- all claimed package managers install on clean machines;
- GitHub private repo and local repo submit exact SHA;
- GitHub tokens never reach guest, RunSpec, logs or receipt.

### Phase 3 — Customer runner and Firecracker execution

Owners: DeepSeek, MiniMax test owner, GPT-6 backend API.

Deliver:
- runner enroll/claim/lease/heartbeat/revoke;
- capacity advertisement and resource reservation;
- Go runner agent;
- Firecracker/jailer/guest images pinned;
- fresh microVM per attempt;
- typed vsock channel;
- source materialization;
- resource and egress enforcement;
- independent teardown;
- evidence/receipt integration.

Exit:
- real KVM Gate B passes on exact commit/artifact digests;
- no strict-to-dev fallback;
- one deterministic run end-to-end from CLI to offline receipt verification.

### Phase 4 — Four-language core QA

Owners: GLM profiles, DeepSeek runtime, MiniMax security matrix.

Deliver:
- Python/pytest profile;
- Node/npm/pnpm/Bun profile;
- Go/go test profile;
- Java/Maven/Gradle profile;
- pinned toolchains and preparation images;
- deterministic app readiness profile;
- test output/evidence parsers;
- resource/time/size bounds.

Exit:
- one passing and one failing fixture per language;
- dependency preparation isolated from sealed testing;
- all results and evidence bound to exact SHA and policy.

### Phase 5 — Deep AI and security modes

Owners: MiniMax privacy/security tests, GPT-6 inference API, DeepSeek runner integration, GLM CLI UX.

Deliver:
- BYOK provider profile;
- OS secret store integration;
- per-org/project and per-run consent;
- runner-side metadata allowlist and sanitizer;
- external provider egress allowlist;
- model output schema validation;
- deterministic ToolGateway authorization;
- AI deep exploration;
- security profile and scoped security tests;
- token/time/cost/tool budgets.

Exit:
- actual outbound payload tests prove no source/secrets are transmitted;
- no consent means no hosted request;
- AI provider failure has no direct fallback;
- prompt injection cannot widen capabilities;
- core mode works without model credentials.

### Phase 6 — Web application implementation

Owners: Gemini frontend, GPT-6 backend.

Precondition: CLI/run/receipt contract and runner gate pass.

Deliver:
- authentication and workspace selection;
- overview;
- projects/repositories;
- run list/detail/timeline;
- runner management;
- findings/evidence/receipt viewer;
- team/role management;
- GitHub integration settings;
- BYOK/privacy settings;
- audit and quota views.

Exit:
- real API data only;
- role/tenant enforcement;
- failure, loading, empty, partial and stale states;
- browser and accessibility checks pass.

### Phase 7 — Scale, reliability and beta

All owners; GPT-6 Luna consolidates acceptance.

Deliver:
- 15 authenticated concurrent clients;
- 45 submission burst;
- multi-tenant fairness and capacity tests;
- runner outage/recovery;
- PostgreSQL restart/recovery;
- provider timeout/quota tests;
- receipt/evidence tamper matrix;
- clean install/upgrade/uninstall;
- SBOM and build provenance;
- incident, rollback, support and retention runbooks.

Exit:
- all release gates in QUALITY-RELEASE-GATES pass;
- no critical/high unresolved security/privacy finding;
- exact release binary, runner image and guest image identities recorded;
- human owner approves beta.

## 3. Critical dependency chain

~~~text
Go CLI core + API contract
        |
        +------ GitHub/local connectors + distribution
        |
Control-plane auth/tenancy + durable run admission
        |
Runner enrollment/claim/lease
        |
Go customer runner + Firecracker/KVM
        |
Guest workload + four language profiles
        |
Evidence + independent teardown + signed receipt
        |
Core CLI release gate
        |
Deep AI/BYOK + security stage acceptance
        |
Dashboard implementation and end-to-end integration
        |
15-user/45-submission + adversarial + release gates
        |
Controlled beta
~~~

The web design system, API design and browser journey mapping happen during the CLI work. Full dashboard build does not block or distract from the critical CLI/sandbox path.

## 4. Resource and scope controls

- No fixed launch date.
- No Workflo-funded execution fleet.
- Customer-owned Linux/KVM compute is default.
- Hosted execution remains disabled until funded.
- BYOK is customer-paid.
- No marketplace, autonomous merge/deploy, multi-VCS, billing or public plugin ecosystem in the first beta.
- Prioritize a dependable single-run vertical slice before adding throughput.
- Measure concurrency and resource usage before publishing capacity claims.

## 5. Phase review checklist

At each phase exit, record:
- exact commit and build;
- changed modules;
- acceptance tests and pass/fail/skip;
- real vs mocked test classification;
- open issues and risk owners;
- protocol/schema compatibility;
- rollback path;
- owner decision.
