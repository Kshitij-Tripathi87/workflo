# Agent path ownership matrix

This is the default write boundary. Each task contract must narrow it further to exact files or directories. A path not listed as owned is read-only unless the coordinator grants a scoped exception.

| Agent | Default write paths | Conditional ownership | Forbidden without separate task |
|---|---|---|---|
| Gemini 4 Hydrogen | agent-workspace/architecture/, agent-workspace/decisions/ | Draft ADR content for review only; do not change ADR status | Product source, schemas, runtime, CI, release, secrets |
| DeepSeek V4.1 Flash-1017 | New crates/workflo-* after language decision | Explicit tickets for worker/, apps/worker-engine/, packages/sandbox-isolation/ | apps/control-plane/, apps/dashboard/, .github/, release publishing, unrelated source |
| MiniMax M3.1 Flash | packages/npm-workflo/, scripts/release/, assigned .github/workflows/ | GitHub adapter paths after API/permission contract approval | Core Rust CLI, Firecracker/cgroup/network code, canonical schema, dashboard |
| GPT-6 Luna | agent-workspace/api/, approved OpenAPI file, assigned contract/acceptance tests | apps/control-plane/, packages/workflo-schema/ only after contract and owner approval | Rust CLI, CI workflow edits, release signing, sandbox policy implementation |
| GLM-5.3 Flash | docs/user-guide/, docs/install/, docs/examples/, agent-workspace/ux/ | apps/dashboard/ only after CLI/API/tenant gates | Rust internals, API/schema source, control plane, worker host, security, CI/release |

## Canonical product paths

| Path | Current role | Write rule |
|---|---|---|
| apps/workflo-cli/ | Existing Python CLI | Keep stable; migration/parity ticket only |
| crates/ | Proposed native Rust workspace | DeepSeek after language spike and approval |
| apps/control-plane/ | Existing FastAPI/PostgreSQL control plane | GPT-6 after approved API contract |
| packages/workflo-schema/ | Proposed Pydantic contract authority | Human ratification required; GPT-6 proposes/tests |
| packages/contracts/ | TypeScript compatibility mirror | No parallel lifecycle authority |
| worker/ | Firecracker/KVM host | Narrow security ticket only, second reviewer and owner approval |
| apps/worker-engine/ | Guest-side engine | DeepSeek implementation, GPT-6 verification |
| apps/sandbox-executor/, supervisor/, packages/sandbox-runtime/ | Development/CI runtime | Never promote to production by fallback |
| packages/npm-workflo/ | Existing npm wrapper | MiniMax |
| apps/dashboard/ | Dashboard client | GLM after API contract and CLI gate |
| backend/, frontend/ | Adjacent Cortex Autopilot | Out of scope |
| client/, server/, shared/, drizzle/ | Legacy | Freeze; no cleanup deletion |
| apps/agent-cli/, apps/validation-cli/ | Unresolved disposition | Read-only pending evidence-backed owner decision |

## General constraints

- Task contract path allowlist overrides this matrix only for that one task.
- No agent relocates or deletes source directories as cleanup.
- CI workflow edits are MiniMax-owned by default; security-sensitive workflow changes need GPT-6 review and human owner approval.
- No two agents edit the same canonical contract simultaneously.
- Root AGENTS.md must retain its Turborepo-managed block; workspace rules supplement it.
