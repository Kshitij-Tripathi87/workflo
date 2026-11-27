# Workflo path ownership matrix

This matrix assigns one primary agent per workstream. Ownership does not override product boundaries, ADRs or the task allowlist. A path may be changed only when a task explicitly names it.

| Repository path | Product role | Primary agent | Supporting/reviewer | Guardrail |
|---|---|---|---|---|
| agent-workspace/ | Agent plans, handoffs and coordination | Gemini (docs steward) | All read; coordinator writes global board | Agents edit only their own plan/handoff branch; global board coordinator-only |
| docs/adr/, docs/architecture.md | Architecture and decisions | Gemini | GPT-6 review | ADR status stays proposed until owner ratifies |
| docs/implementation/, docs/reconciliation/ | Blueprint/status evidence | Gemini | GPT-6 | Status updates must cite current implementation/test evidence; do not rewrite historical baselines |
| packages/workflo-schema/ | Canonical contracts | DeepSeek on assigned task | Gemini design, GPT-6 tests | Protected shared contract; owner decision required for version/state semantics |
| packages/contracts/ | TypeScript contract mirror | GLM on bounded mirror task | GPT-6 | Must pass parity against canonical schema exports |
| worker/ | Production Firecracker/KVM host | DeepSeek | GPT-6 tests, Gemini read-only architecture review | P0 security boundary; no fallback; real KVM proof required |
| apps/worker-engine/ | Guest-side execution | DeepSeek | GPT-6 | Guest never receives host signing keys |
| supervisor/ | Development/CI daemon and IPC | DeepSeek | GPT-6 | Preserve CLI imports/protocol compatibility |
| packages/sandbox-runtime/ | Development/CI namespace runtime | DeepSeek | GPT-6 | Never describe as production microVM boundary |
| apps/sandbox-executor/ | Docker development executor | DeepSeek | GPT-6 | No second Firecracker host; dev-only boundary |
| apps/control-plane/app/services/dispatch_service.py and queue integration | Durable dispatch/orchestration | MiniMax | DeepSeek, GPT-6 | No auth/crypto/RLS changes without separate high-risk ticket |
| apps/control-plane/app/api/ | API integration | MiniMax for bounded orchestration only | GPT-6, Gemini | Auth, key provisioning, identity and security endpoints require explicit owner assignment |
| apps/control-plane/app/core/crypto.py, security.py, envelope.py | Security-sensitive control-plane code | No standing model owner | Gemini + GPT-6 read-only review; human approval | Do not modify incidentally |
| apps/control-plane/db/ and db/rls/ | Database, RLS and migration code | MiniMax only on explicit ticket | DeepSeek + GPT-6 review | Migration/backfill/tenant tests required |
| apps/workflo-cli/ | Canonical CLI implementation | DeepSeek | GLM UX, GPT-6 tests | Avoid duplicate workflo entry points |
| apps/dashboard/ | Workflo dashboard shell | GLM after evidence workflow stabilizes | Gemini visual review, GPT-6 tests | No new feature screens before workflow stabilization |
| website/ | Workflo marketing/docs content | GLM | Gemini copy/architecture review | Do not displace runtime/security work |
| .github/workflows/, scripts/ci/, scripts/release/ | CI, release and automation | MiniMax | GPT-6 | No ignored failure/continue-on-error to manufacture green builds |
| packages/npm-workflo/, install.sh, install.ps1 | CLI packaging/install | MiniMax | GLM docs, GPT-6 tests | No release publishing without human approval |
| test directories across active components | QA and regression | GPT-6 when assigned | Implementer | One writer per test path; reviewers do not silently patch the implementer's branch |
| docs/, README.md, SECURITY.md | Developer docs and controls | GLM for prose; Gemini for architecture docs | GPT-6 factual consistency | Docs must distinguish dev vs production profile and proven vs planned |

## Unassigned or prohibited-by-default paths

- backend/ and frontend/: adjacent Cortex Autopilot; no new Workflo Trust MVP feature work.
- client/, server/, shared/, drizzle/, action/, examples/, ci-templates/: legacy/archive; do not extend without explicit re-adoption.
- packages/sandbox/, packages/ingestor/, packages/executor/: frozen TypeScript runtime lineage pending Gate B; keep compatibility/CI only.
- infra/: reference manifests until a service owner re-adopts and validates them.
- apps/agent-cli/ and apps/validation-cli/: disposition unresolved; do not delete, merge or make canonical by assumption.
- deploy/*.env.example: keep aligned with control-plane config; never place real credentials there.
- .env*, private data, data/, model weights, local caches, signing key material: not agent-editable or model-readable by default.

## Conflict resolution

If a task spans two ownership areas, the coordinator must:
1. name one implementation owner;
2. list every touched path;
3. name the supporting owner and review-only scope;
4. define merge order and interface contract;
5. split the task if both owners need to write overlapping files.

Model identity alone does not grant authority to change a path.
