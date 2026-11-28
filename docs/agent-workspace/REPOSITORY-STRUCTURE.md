# Workflo Repository Restructuring and Shared Workspace Rules

## 1. Objective

Organize the existing Workflo monorepo so five agents can work in parallel without creating duplicate systems, changing unrelated Cortex Autopilot code, corrupting Git state or breaking existing release evidence.

This is a controlled restructuring of ownership and new module boundaries. It is **not** permission to move the entire historical repository or delete working Python packages.

## 2. Current repository facts

The current main branch contains:

- Python CLI at apps/workflo-cli.
- npm wrapper at packages/npm-workflo, which currently creates a Python virtual environment and installs vendored wheels. It requires Python 3.11+ and invokes the Python executable.
- Python control plane at apps/control-plane, using FastAPI, SQLAlchemy and PostgreSQL-oriented persistence. Current code also contains development defaults; production guards must be audited.
- Firecracker/KVM host foundation under worker/ (Python).
- Guest worker under apps/worker-engine (Python).
- Shared Pydantic/schema contracts under packages/workflo-schema.
- Development-only Docker and namespace paths under apps/sandbox-executor and packages/sandbox-runtime.
- Next.js dashboard under apps/dashboard.
- Local model scaffolding under workflo-ai-integration.
- Adjacent Cortex Autopilot under backend/ and frontend/; do not extend those for Workflo Trust.

The existing npm package is not yet a native binary distribution: bin/workflo.js launches a package-local Python virtualenv, and postinstall creates that environment and installs wheels. The new native release must eliminate this Python installation dependency for the CLI client.

## 3. Proposed target tree

Create new modules alongside existing paths; migrate incrementally.

~~~text
workflo/
├── apps/
│   ├── workflo-cli/                 # existing Python CLI; compatibility/reference until parity
│   ├── workflo-cli-go/              # NEW canonical native CLI
│   │   ├── cmd/workflo/
│   │   ├── internal/app/
│   │   ├── internal/commands/
│   │   ├── internal/config/
│   │   ├── internal/auth/
│   │   ├── internal/api/
│   │   ├── internal/source/
│   │   ├── internal/output/
│   │   └── internal/update/
│   ├── workflo-runner-go/           # NEW canonical customer runner host agent
│   │   ├── cmd/workflo-runner/
│   │   ├── internal/agent/
│   │   ├── internal/claim/
│   │   ├── internal/firecracker/
│   │   ├── internal/jailer/
│   │   ├── internal/guestchannel/
│   │   ├── internal/resources/
│   │   ├── internal/network/
│   │   ├── internal/teardown/
│   │   └── internal/evidence/
│   ├── control-plane/               # existing FastAPI backend; extend via API contracts
│   ├── worker-engine/               # existing guest engine/adapters; preserve until migration is proven
│   └── dashboard/                   # Next.js UI, substantial implementation after CLI gate
├── packages/
│   ├── workflo-schema/              # canonical Python schema source initially
│   ├── workflo-protocol-go/         # NEW generated/validated Go bindings
│   ├── workflo-policy-go/           # NEW deterministic policy evaluator (MiniMax-owned)
│   ├── npm-workflo/                 # migrate to native binary distribution
│   ├── sandbox-runtime/             # dev/CI only
│   └── sandbox-isolation/            # legacy/reference until migration disposition
├── profiles/
│   ├── python/
│   ├── node/
│   ├── go/
│   └── java/
├── tests/
│   ├── contracts/
│   ├── e2e/
│   ├── installation/
│   ├── security/
│   ├── chaos/
│   └── performance/
├── security/
│   ├── threat-model/
│   ├── policies/
│   └── adversarial-fixtures/
├── docs/
│   ├── adr/
│   ├── agent-workspace/
│   ├── architecture/
│   └── release/
├── go.work                         # NEW Go workspace; added only once modules exist
└── go.work.sum                     # generated
~~~

The directory tree is a target proposal. Create only the directories needed for accepted implementation tickets. Do not create empty scaffolding everywhere.

## 4. Five-model ownership map

| Agent | Owned paths | Review only / forbidden paths |
|---|---|---|
| DeepSeek | apps/workflo-cli-go core/runtime packages; apps/workflo-runner-go; Go protocol integration | No policy self-approval; no dashboard or backend DB ownership; no canonical schema edits without approval |
| GLM | CLI command handlers/UX package boundary agreed with DeepSeek; GitHub/local connector modules; packages/npm-workflo; profiles/ and installer tests | No Firecracker host implementation; no policy gates; no dashboard or backend migrations |
| MiniMax | packages/workflo-policy-go; security/; tests/security/; tests/chaos/ security fixtures and inference outbound-payload tests | No main runtime implementation in DeepSeek-owned paths; no production authority or self-approval |
| Gemini | apps/dashboard/; dashboard tests and design system; docs/ui-journeys/ | No control-plane auth/DB code; no runner access; no real data fabrication |
| GPT-6 Luna | apps/control-plane/; API contract/OpenAPI plan; database migrations/RLS/API tests; docs/api/ | No Go host runner implementation; no UI component ownership; no unilateral canonical receipt/lifecycle contract edits |

Shared schema source remains human-approved. Affected agents can propose schema changes, but cannot unilaterally redefine lifecycle, receipts, policy or guest/host protocol.

## 5. One repository, separate worktrees

All five agents use the same repository and shared workspace parent. They must **not** use the same mutable checkout at the same time. Shared physical Git index and working-tree state can cause accidental staging, checkout collisions and overwrites.

Recommended parent:

~~~text
/workspace/
├── workflo/                               # canonical integration checkout
└── .workflo-worktrees/
    ├── deepseek-native-cli-runner/
    ├── glm-cli-connectors-distribution/
    ├── minimax-sandbox-security-qa/
    ├── gemini-dashboard-frontend/
    └── gpt6-luna-backend-platform/
~~~

This is one monorepo and one Git object database with separate working directories, not five repo copies.

### Remote branch names

- agent/deepseek-native-cli-runner
- agent/glm-cli-connectors-distribution
- agent/minimax-sandbox-security-qa
- agent/gemini-dashboard-frontend
- agent/gpt6-luna-backend-platform

The current older branch names from the previous planning draft are superseded. Do not start new implementation from:
- agent/glm-cli-connectors
- agent/deepseek-execution
- agent/minimax-security-inference
- agent/gemini-dashboard
- agent/gpt6-luna-qa-release

Those branches were created for an earlier, now-replaced ownership split. Use the new branches listed above.

### Worktree bootstrap

First fetch the approved planning branch and all agent refs, then create each worktree from its remote-tracking branch:

~~~bash
git fetch origin --prune
mkdir -p ../.workflo-worktrees

git worktree add --track -b agent/deepseek-native-cli-runner \
  ../.workflo-worktrees/deepseek-native-cli-runner \
  origin/agent/deepseek-native-cli-runner

git worktree add --track -b agent/glm-cli-connectors-distribution \
  ../.workflo-worktrees/glm-cli-connectors-distribution \
  origin/agent/glm-cli-connectors-distribution

git worktree add --track -b agent/minimax-sandbox-security-qa \
  ../.workflo-worktrees/minimax-sandbox-security-qa \
  origin/agent/minimax-sandbox-security-qa

git worktree add --track -b agent/gemini-dashboard-frontend \
  ../.workflo-worktrees/gemini-dashboard-frontend \
  origin/agent/gemini-dashboard-frontend

git worktree add --track -b agent/gpt6-luna-backend-platform \
  ../.workflo-worktrees/gpt6-luna-backend-platform \
  origin/agent/gpt6-luna-backend-platform

git worktree list
~~~

If a local branch already exists, do not use -b again. Check it out only in one worktree. The integrator must never check out an agent's branch in the canonical integration checkout while the agent is working.

## 6. Branch/PR protocol

- Every agent has one dedicated branch/worktree.
- Each PR addresses bounded plan IDs and one coherent slice.
- Main is protected; no agent direct-push to main.
- The integrator merges one PR at a time and reruns affected gates.
- No force push after review unless an owner explicitly requests it.
- Keep agent branches rebased on a common integration base at defined checkpoints.
- Contract changes are implemented as coordinated producer/consumer PRs or a single integration PR.
- No PR may move source directories, rename the canonical worker or alter old receipt verification without an approved migration plan.

## 7. Migration rules

### Python-to-Go CLI

1. Freeze current CLI command/flag/exit-code behavior as acceptance fixtures.
2. Define Go API and config compatibility.
3. Build Go CLI skeleton and one vertical command.
4. Implement command parity in bounded groups.
5. Add cross-platform installers.
6. Run old Python and new Go CLI against the same safe fixtures and compare contracts.
7. Make Go canonical only after parity, install and receipt verification gates pass.
8. Keep old Python command available during a deprecation window; remove only through a later approved release.

### Python-to-Go runner

1. Keep the current worker/ code as the baseline.
2. Freeze assignment, host operation and guest protocol schemas.
3. Implement one Go host lifecycle operation at a time.
4. Use the same real KVM fixtures and teardown evidence.
5. Run differential/contract tests against the Python reference behavior.
6. Switch only after Gate B passes on the Go runner.
7. Retire Python host code only after a separate parity and rollback review.

Do not run two independent production VM managers for the same runner identity.

### Existing npm wrapper

Current packages/npm-workflo invokes a Python venv in postinstall. Replace this with a native-binary distribution architecture:
- platform-specific optional binary packages;
- JS shim only for locating and invoking the binary;
- no Python requirement;
- no arbitrary network-fetch install script by default;
- release artifacts carry SHA-256 and cryptographic provenance;
- package-manager tests run for npm, pnpm and Bun.

Preserve the old package name as a compatibility/deprecation path if published users exist. Verify the intended @workflo scope/namespace before publishing; do not assume registry-name availability.

## 8. What must not be touched

- Do not extend backend/ or frontend/; these are adjacent Cortex Autopilot paths.
- Do not make marketing website/Cloudflare backend share product-control-plane credentials or database.
- Do not delete working Python tests, packages or receipt verifiers before Go parity.
- Do not mark Docker, WSL2, bwrap or a local namespace as strict microVM.
- Do not change accepted ADR-0022 behavior without a new approved ADR.
- Do not reformat or mass-rename unrelated code.
- Do not commit generated binaries, customer artifacts, source snapshots, secrets or test credentials.
- Do not add unreviewed CGO/native dependencies to the CLI.
- Do not give agents access to production keys, billing or deployment controls.

## 9. Workspace task lifecycle

Each task must be:
- scoped to a single owner;
- linked to an architecture or acceptance requirement;
- bounded to a specific path/module;
- explicit about allowed and forbidden files;
- testable;
- reviewable independently.

States:
BACKLOG -> READY -> IN_PROGRESS -> REVIEW -> INTEGRATION -> ACCEPTED

BLOCKED is a separate state with a named dependency. “Code generated” is not a task state.

## 10. Completion requirements

A branch is integration-ready only when:
- tests for changed behavior pass;
- negative/security tests execute, not skip;
- build and static checks pass;
- no unrelated scope changes exist;
- API/schema compatibility is proven;
- security impact is documented;
- exact base SHA and test commands are included;
- a different agent reviews the implementation;
- human approval exists for high-impact boundaries.
