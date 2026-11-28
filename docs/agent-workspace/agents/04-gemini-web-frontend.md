# Agent 04 — Gemini 4 Hydrogen
## Workflo Web Application, Frontend Architecture, UI/UX and Browser QA

**Workstream:** web app — frontend  
**Branch:** agent/gemini-dashboard-frontend  
**Primary owner:** Gemini 4 Hydrogen  
**Reviewers:** GPT-6 Luna (API/backend contract), GLM (CLI parity/user workflow), GPT-6 Luna and human owner (acceptance).

## 1. Why this model owns this work

Google's official Gemini 4 Hydrogen model card reports:
- SWE-sweep: **13.5%**
- Terminal-Bench 4.1 cheating-adjusted: **57.0%**
- AutomationBench-AA: **76.1%**
- OSWorld-2.1 offline subset: **77.6%**
- Agents' Last Exam v1.1: **71.6%**

Google explicitly lists web development, fast disciplined execution, iterative repository coding/debugging, open-ended agentic execution and multimodal knowledge work as intended usage.

Primary source: https://deepmind.google/models/model-cards/gemini-4-hydrogen/

**Routing hypothesis:** UI implementation, iterative visual/browser workflows and frontend integration. These scores do not prove visual taste or accessibility. Workflo's own browser tests, design review and user acceptance decide quality.

## 2. Mission and sequencing

Design and then implement the Workflo dashboard as an operational companion to the CLI. The web app must use the same APIs, contracts, lifecycle and trust outcomes.

**Important sequencing:**
- During CLI phase: audit dashboard, create information architecture, API dependency map, design system and user journeys. Build a small design prototype using clearly labelled synthetic fixtures if useful.
- Do not invest in full dashboard feature implementation until the CLI/run/receipt vertical slice and API contracts are accepted.
- After CLI gate: implement dashboard screens against real control-plane APIs.

The dashboard is not a separate execution engine.

## 3. Owned paths

Primary:
- apps/dashboard/
- dashboard-specific unit/component/browser tests.
- docs/ui-journeys/ and dashboard design tokens if approved.
- dashboard-only mock fixtures clearly labelled as test fixtures.

Must not own:
- apps/control-plane/ API/auth/database code (GPT-6).
- apps/workflo-cli-go/ or runner.
- worker/ or Firecracker.
- canonical schema source.
- marketing website or Cloudflare D1 backend.
- tenant authorization or security gate changes.

## 4. Mission-critical UX principles

- Show the real run state, not a simplified green/red abstraction.
- Keep execution, QA and trust separate.
- Every display element is explainable by an API field or a clearly labelled local UI-only state.
- Never show fabricated metrics, fake runner health or simulated successful run in production.
- Make queues, missing capacity, cancellation and incomplete evidence visible.
- Never hide trust or teardown failure behind a successful test badge.
- Use accessible contrast, keyboard paths, responsive layout and reduced motion.
- Treat logs, filenames, test names and artifact content as untrusted input.

## 5. Product surfaces

### GEM-01 — Audit and information architecture (pre-CLI gate)

- Inspect apps/dashboard structure, existing layouts/routes/components, auth setup and dependency versions.
- Map every existing route to current API/contract support.
- Identify mock/demo data and prevent it being presented as real.
- Define role and permission assumptions with GPT-6.
- Produce screen map, route map, API dependency matrix and error-state taxonomy.

Deliverable: design/IA document. No full UI build yet.

### GEM-02 — Design system (pre-CLI gate)

Create:
- typography scale;
- spacing and layout tokens;
- semantic colors for queued/running/rejected/execution failed/QA failed/trust failed/verified;
- button/input/form conventions;
- tables, cards and detail panels;
- empty/loading/error/partial skeleton states;
- accessible status announcements;
- light/dark support only if it does not delay core UX; Workflo's dark identity is default.

Avoid decorative gradients/glassmorphism, generic SaaS widgets and oversized analytics cards. Workflo is an engineering trust product; the interface should feel precise, operational and evidence-oriented.

Deliverable: token set, shared components and representative static screens/prototype.

### GEM-03 — Overview dashboard (after CLI gate)

Show:
- projects/workspaces;
- active/queued runs;
- recent results;
- runner availability;
- trust verification incidents;
- usage/quota and capacity information if API supports it.

No made-up data. If an API is absent, surface a disabled/coming-soon state in a development environment, not production fake metrics.

### GEM-04 — Projects and repositories

- Individual and organization workspace switch.
- GitHub installations and selected repositories.
- connection scope and status.
- project default policy/profile.
- runner pool binding.
- permission/revocation state.

Only show a repo connected when backend confirms installation scope and read access.

### GEM-05 — Runs list

- search and filters by workspace/project/repository/commit/state/stage/date;
- cursor pagination;
- clear queued/admitted/running/completed/rejected/cancelled/incomplete states;
- separate QA verdict and trust outcome;
- no status guessed from missing fields.

### GEM-06 — Run detail

Display:
- run ID and attempt ID;
- repository and exact commit SHA;
- policy/runtime/guest image digests;
- selected profiles and resource budget;
- canonical lifecycle timeline;
- stage-by-stage core/deep/security status;
- test counts and reproducible findings;
- agent activity only as bounded authorized metadata;
- evidence manifest and signed receipt;
- independent verification and teardown status.

A verified failing test should be understandable as a valid QA failure. An infrastructure or trust failure must not be called a product finding or a pass.

### GEM-07 — Runner management

- runner name/identity;
- organization/project/pool association;
- OS/architecture and KVM eligibility;
- Firecracker/jailer and guest image digest;
- capacity and active runs;
- last heartbeat;
- online/offline/draining/revoked status;
- install/enroll instructions;
- revoke/drain actions only when role/API authorizes them.

No host terminal or arbitrary remote shell in the dashboard.

### GEM-08 — Evidence and receipt viewer

- receipt signature status;
- trusted key fingerprint;
- run/attempt/source/policy binding;
- evidence manifest tree;
- download authorization;
- trust/teardown status;
- explain what verification proves and does not prove.

Render logs as escaped text. Never treat logs/artifacts as HTML or execute links/scripts embedded in outputs.

### GEM-09 — Team, integration and privacy settings

- user profile and personal workspace;
- organization switch;
- members and roles;
- GitHub app installation and repository scope;
- provider profile alias and model identifier;
- BYOK secret set/rotate/delete workflow;
- consent policy and provider data handling;
- usage/capability quotas;
- audit events.

Secrets are write-only. Frontend never receives provider or GitHub secret values.

### GEM-10 — Browser acceptance

Test:
- desktop and mobile layout;
- keyboard-only navigation;
- focus order and dialog return focus;
- screen reader label/announcements;
- 401/403/404/409/429/5xx;
- stale/partial responses;
- cancellation;
- large run timelines;
- pagination;
- revoked GitHub app;
- offline runner;
- incomplete evidence;
- trust failure;
- XSS attempts through log/artifact fields.

## 6. API rules

- Use GPT-6 Luna's approved OpenAPI/type generation.
- One authenticated API client layer.
- No direct connection to runner or guest service.
- No marketing site D1 or Cloudflare backend use.
- No tenant identity trusted from local storage.
- Use API server authorization for every mutation and data access.
- Keep mutations idempotent where the API contract supports it.
- Respect request cancellation, pagination and server retry-after.
- Do not fabricate endpoint fields or status semantics.

## 7. Frontend quality gates

- lint and typecheck clean.
- production build.
- component tests.
- API-client schema validation.
- browser E2E for primary flows.
- accessibility tests.
- visual snapshot checks on representative states.
- performance on run-list/detail pages with large bounded data.
- XSS-safe rendering.
- role-based UI and server rejection both tested.

## 8. Stop/escalation

Stop and request API owner change rather than inventing an endpoint. Escalate if a screen requires broad runner privileges, secret exposure, unsupported status mapping, fake success, bypassing org membership or reading cross-tenant resources.

## 9. Definition of done

A user can sign in, select a personal/org workspace, view connected GitHub projects, see real runs, understand the full lifecycle and three outcomes, inspect/download authorized evidence and see runner health/settings without the frontend bypassing backend authorization.
