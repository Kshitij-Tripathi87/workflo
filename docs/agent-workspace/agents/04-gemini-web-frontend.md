# Agent 04 — Gemini 4 Hydrogen
## Workflo Dashboard Architecture, Design System, Frontend Delivery and Browser QA

**Workstream:** Dashboard UX, frontend and browser quality  
**Branch:** `agent/gemini-dashboard-frontend`  
**Implementation owner:** Gemini 4 Hydrogen  
**Contract owner/reviewer:** GPT-6 Luna  
**CLI workflow reviewer:** GLM-5.3 Flash  
**Security/privacy reviewer:** MiniMax M3.1 Flash  
**Human approver:** Product owner  
**Primary product gate:** substantial implementation is blocked until the CLI → real Firecracker/KVM → independently verified receipt milestone (M1) is accepted.

---

## 1. Mission and expected outcome

Create the Workflo web application as an operational companion to the native Go CLI. It must expose the same verified product state as the CLI and control plane; it must not become a second execution engine, invent lifecycle states, or make unsupported security claims.

The eventual dashboard should let a user:
1. sign in and select an individual or organization workspace;
2. create/select a project and connect an authorized GitHub repository;
3. understand runner availability and eligibility;
4. view queued, active and completed runs;
5. inspect execution status, QA outcome and trust outcome independently;
6. inspect Core, Deep AI and Security gate results separately;
7. understand reproducible findings and their verification status;
8. inspect/download authorized evidence and verify receipt status;
9. manage workspace membership, roles, source integrations and BYOK consent;
10. view audit events, quotas and capacity where APIs exist.

**Sequencing:** while M1 is in progress, perform repository audit, information architecture, design-system preparation, typed API mapping and static synthetic prototypes only. Do not build real operational screens against guessed fields. Substantial dashboard implementation starts after the CLI/runner/receipt milestone and the API/tenant prerequisites in this plan pass.

## 2. Why this model owns this work

Google DeepMind's Gemini 4 Hydrogen model card reports:
- SWE-sweep: 13.5%;
- Terminal-Bench 4.1 cheating-adjusted: 57.0%;
- AutomationBench-AA: 76.1%;
- Agents' Last Exam v1.1: 71.6;
- OSWorld-2.1 offline subset: 77.6%.

Google lists web development and agentic workflows among intended uses. Automation and computer-use scores support the browser/iterative workflow assignment. They do not measure visual taste, accessibility or dashboard maintainability; those require Workflo-specific calibration, screenshot/browser review and human product acceptance.

Source: https://deepmind.google/models/model-cards/gemini-4-hydrogen/

Do not compare Terminal-Bench 4.1 directly with Terminal-Bench 4.0 or 2.1 results from other vendors.

## 3. Ownership and protected boundaries

### Owned paths after the dashboard gate
- `apps/dashboard/` — existing Next.js dashboard shell and approved frontend implementation.
- `apps/dashboard/tests/` or the existing component/e2e test locations.
- Dashboard-only typed client consumption and view models generated from GPT-6's API contract, subject to path reservation.
- `docs/agent-workspace/ui/` — information architecture, journeys, component specs and UX acceptance.
- Synthetic frontend fixtures clearly segregated from production API data.

### Read-only or proposal-only paths
- `apps/control-plane/`, schemas, migrations, auth and RLS: GPT-6 owns.
- `apps/workflo-cli-go/`, `apps/workflo-runner-go/`, `worker/`: DeepSeek owns.
- `packages/workflo-policy-go/`, `security/`, `tests/security/`: MiniMax owns.
- CLI commands/connectors/packages: GLM owns.
- Canonical Pydantic lifecycle/receipt/RunSpec fields: human-approved contract owner only.

### Forbidden
- No direct connection from browser to runner/guest/vsock.
- No direct database access or client-controlled tenant authorization.
- No localStorage workspace ID treated as authority.
- No mock “live” run data, fake runner health, fabricated load metrics or fake successful receipts in production UI.
- No hosted source prompt, raw source/log display to unauthorized users, BYOK key retrieval or GitHub credential exposure.
- No UI mutation that bypasses server authorization.
- No dashboard feature implementation before M1 and API prerequisites pass.
- No deployment, production publish or environment/secret changes.

## 4. Gate 0 — pre-implementation audit and UX preparation

### GEM-00 — Dashboard current-state audit
Inspect:
- actual app routing/layout and Next.js version;
- current authentication/client assumptions and middleware;
- existing API helper, generated types and fetch patterns;
- styling/tokens/components and dependency versions;
- route-level mocks, demo fixtures and placeholder content;
- build/lint/typecheck/test CI jobs;
- current dashboard navigation and unused links.

Deliverables:
- route/screen inventory;
- component inventory and duplication list;
- API endpoint/field dependency matrix;
- auth/session/data-fetch flow;
- mock-data classification;
- accessibility/performance baseline;
- exact build/test baseline at immutable SHA.

Acceptance: every displayed production field has a known API source or is removed/labelled as static prototype. No UI source change in the audit PR.

### GEM-01 — User journeys and information architecture
Document flows for:
1. first login and individual workspace;
2. switch to organization workspace;
3. create/select project;
4. GitHub App installation and repository selection;
5. runner enrollment/eligibility;
6. create run and inspect preview;
7. queued/run-in-progress states;
8. Core/Deep/Security gate completion and failure;
9. findings triage and reproduction;
10. evidence manifest and offline receipt verification;
11. BYOK credential write/rotate/delete;
12. explicit metadata-only hosted consent;
13. membership/invitation/role change;
14. audit and usage/capacity inspection.

For each journey specify:
- entry point and prerequisite;
- actor and required role;
- API requests;
- loading/empty/stale/partial/error states;
- confirmation or high-impact action;
- expected navigation/URL behavior;
- user-visible success and failure;
- cancellation/recovery;
- accessibility announcements;
- data privacy class.

Acceptance: screen map includes all required states and clearly labels unavailable product functionality. API dependency is mapped to actual endpoint or marked BLOCKED.

### GEM-02 — Design system preparation
Create a compact, production-oriented design system rather than a generic dashboard kit.

Define:
- typography roles and hierarchy (page title, section, table, metadata, code/digest);
- spacing/layout scale, content width and density rules;
- semantic surface/background/border/text tokens;
- status taxonomy with independent visual semantics for Execution, QA, Trust and Core/Deep/Security;
- table, filter, pagination, tabs, forms, dialogs and notification patterns;
- code/digest/commit display and copy controls;
- evidence tree and timeline primitives;
- empty/loading/skeleton/stale/error/permission-denied states;
- responsive breakpoints and reduced-motion behavior;
- focus, keyboard and screen-reader conventions.

Visual rules:
- engineering-first, high information clarity;
- dark identity is default unless existing design tokens dictate otherwise;
- no decorative gradient/glass UI, fake charts or oversized hero-stat cards;
- avoid a single green “success” badge that conflates QA, execution and trust;
- long SHAs/digests must be readable, copyable and safely truncated;
- status always has text, not color alone.

Deliverables: token specification, component inventory with prop contracts, Figma/static prototypes or equivalent code-based design preview, visual state sheets and accessibility plan. Do not create production data/API dependencies.

## 5. Dashboard information architecture

Proposed top-level navigation (confirm only against real API capabilities):
- Overview
- Projects
- Runs
- Runners
- Evidence
- Team
- Settings
- Audit

Hide or disable navigation sections whose backend contract is not approved/implemented. No dead links or fake placeholder routes in production.

### Screen specifications

#### UI-01 — Authentication and workspace selection
- login/device authorization return handling;
- clear account identity and session expiry;
- personal workspace distinct from organization;
- workspace switcher shows role and membership state;
- no client-supplied workspace ID can grant access;
- expired/revoked session recovery.

#### UI-02 — Overview
- active/queued run count only from API aggregate;
- recent runs with real source SHA and outcome axes;
- runner eligibility/heartbeat summary only if server supports it;
- unresolved trust incidents and incomplete evidence;
- capacity/quota data with timestamp and source;
- empty state for new workspace;
- no synthetic values in production.

#### UI-03 — Projects and repositories
- create/select/archive project (role-gated);
- connected GitHub installation and repository scope;
- local project identity if supported by API;
- default profile/policy/runner selection;
- connection permissions, revoked installation and expired state;
- no raw token or private key in page state.

#### UI-04 — Runner list/detail
- runner identity/version, OS/architecture/kernel;
- strict eligibility and exact reason if ineligible;
- KVM capability and pinned Firecracker/jailer/guest digests;
- capacity after reservation, active leases and heartbeat age;
- online/offline/draining/revoked state;
- safe enroll/drain/revoke actions by role;
- never expose host shell, terminal or raw filesystem paths.

#### UI-05 — Runs list
- cursor pagination and server-side filters;
- repository, full commit SHA, project, profile and requested gates;
- queue/run duration and runner target;
- independent Execution, QA and Trust columns;
- filters preserve URL state only if API contract supports it;
- no local aggregation that mislabels missing state.

#### UI-06 — Run detail
Sections:
1. Source identity: provider, canonical repo, full commit SHA, source digest.
2. Run/attempt IDs and status.
3. Policy/profile/runtime/guest image digests.
4. Lifecycle timeline: admission, claim, provision, guest ready, execution, evidence, teardown, signing.
5. Core gate, Deep AI gate and Security gate separately.
6. Execution state, QA outcome and Trust outcome separately.
7. Findings: candidate/reproduced/verified/accepted/rejected; repro steps and evidence.
8. Resource summary and runner identity.
9. Evidence manifest and downloadable artifacts if authorized.
10. Receipt signature/trust-anchor/evidence-verification report and limitations.

Explain valid combinations:
- execution completed + QA failed + trust verified can be a valid trustworthy test failure;
- execution completed + QA pass + trust incomplete is not an overall trusted pass;
- a skipped required gate cannot render green.

#### UI-07 — Findings
- finding category/severity and source run/attempt;
- reproduction status and reproducible evidence;
- candidate vs accepted finding distinction;
- triage/acknowledgement only where API authorizes;
- no direct edit/patch/merge from dashboard in beta;
- show model-generated observation as model-assisted candidate, never proof.

#### UI-08 — Evidence and receipt
- evidence manifest hierarchy with file type, size, digest and producer;
- authorized download, explicit size and content classification;
- signed receipt envelope summary and signer fingerprint;
- trusted key status, offline verifier result and evidence completeness;
- distinguish signature valid from trust claim valid;
- display missing/unknown teardown checks;
- logs are untrusted text and rendered escaped; no HTML/script execution.

#### UI-09 — Team/membership
- invite/accept/revoke, role change, membership state;
- Owner/Admin/Developer/Viewer action-level capability;
- self-removal/last-owner/ownership transfer rules as API defines;
- confirmation and audit summary for privileged changes;
- server response is authoritative; hiding a button is not authorization.

#### UI-10 — Integrations and privacy
- GitHub installation identity/scope/repositories;
- revoked/expired/missing permission states;
- BYOK provider alias/model ID and last rotation metadata;
- secret set/update is write-only; no secret readback;
- hosted prompt consent shows the exact permitted metadata categories and data handling;
- no “consent” control may imply source/diff/log transmission is allowed;
- default consent false.

#### UI-11 — Audit/usage
- immutable event ordering and pagination;
- actor, resource, action, result, timestamp, correlation ID;
- redact secrets and sensitive payloads;
- usage/quota/capacity only if supplied by API;
- export access and retention behavior visibly documented.

## 6. API contract rules

- Consume the approved OpenAPI schema and generated/validated TypeScript client.
- Use one authenticated API client and centralized error parsing.
- Never call runner/guest services directly.
- Never derive tenant authority from local storage or request body.
- Every resource query uses active verified workspace context from backend session.
- Mutations require server permission and idempotency where supported.
- Handle 401/403/404/409/422/429/5xx and Retry-After; distinguish access denied from not found without leaking cross-tenant existence.
- Use abort signals and cleanup for requests on navigation.
- Cursor pagination must follow API order and cursor semantics.
- Stale status must have timestamp/refresh behavior; do not assume real-time push if API is polling.
- No generated fake API values or optimistic updates for security-critical states.
- Do not invent fields/enums. Raise a contract change to GPT-6.

## 7. Browser, accessibility and security test plan

### Functional browser flows
- sign in/out/session expiry;
- personal workspace and organization switch;
- create/select project;
- GitHub installation connection and revoked state;
- run list pagination/filter;
- run detail with multiple independent outcome combinations;
- queued/running/cancel request;
- incomplete evidence and invalid receipt;
- role-limited member/settings screens.

### Accessibility
- keyboard-only navigation;
- visible focus and logical focus order;
- focus trap and restoration for dialogs;
- screen-reader labels/status announcements;
- semantic headings/table labels;
- contrast and color-independent status;
- zoom/reflow and reduced motion;
- WCAG 2.2 AA checklist.

### Frontend security
- XSS strings in repo names, branch names, test names, finding messages, logs and evidence filenames;
- URL/Markdown injection in untrusted text;
- unsafe download link/filename behavior;
- unauthorized API response handling;
- cross-tenant guessed IDs return safe not-found/denied behavior;
- secret values absent from frontend bundles, state, console and error telemetry;
- HTML escaping and no unsafe rendering.

### Performance
- run lists at 10, 100, 1,000 and bounded large records via fixture/API tests;
- large evidence tree virtualization/limits;
- no unbounded event subscriptions/poll loops;
- image/font/script weight and route loading budgets;
- no repeated N+1 frontend API fetch patterns.

### Visual regression
- snapshots for light/dark if both supported;
- 1440 desktop, laptop, tablet and mobile;
- loading/empty/partial/error/permission-denied states;
- long SHA/digest/repository names;
- failed QA with trust verified;
- passed QA with trust incomplete;
- queued and runner-ineligible state.

## 8. Work packages and acceptance

| ID | Stage | Deliverable | Acceptance |
|---|---|---|---|
| GEM-00 | Pre-M1 | Current dashboard audit | Exact routes/components/API/mocks/CI baseline |
| GEM-01 | Pre-M1 | Journey/IA specification | All actors, states, error/recovery and API dependencies mapped |
| GEM-02 | Pre-M1 | Design system and prototypes | Typed component specs, status taxonomy, responsive/accessibility plan; static synthetic data only |
| GEM-03 | Pre-M1 | Frontend API integration plan | No guessed routes; generated client path and auth boundaries documented |
| GEM-04 | Post-M1 | App shell, auth and workspace | Individual/org identity, session expiry and role-aware navigation pass |
| GEM-05 | Post-M1 | Projects and integrations | Real repository scopes and server-authorized mutations |
| GEM-06 | Post-M1 | Runs list/detail/timeline | Canonical states and outcome axes displayed correctly |
| GEM-07 | Post-M1 | Runner UI | Eligibility, capacity, heartbeat and revoke/drain permission behavior |
| GEM-08 | Post-M1 | Findings/evidence/receipt | Candidate/verified states, evidence integrity and safe rendering |
| GEM-09 | Post-M1 | Team/settings/audit | Role matrix and write-only secrets/privacy consent correct |
| GEM-10 | Acceptance | Browser/accessibility/performance | Required CI suite passes across core screens and edge states |

Every post-M1 work package gets a separate task contract and PR; do not implement all dashboard pages in a single broad diff.

## 9. Handoff requirements

Each PR includes:
- task ID, base/head SHA and changed route/component list;
- API contract version and endpoints used;
- role/permission assumptions;
- screenshot/screen recording at specified viewport;
- browser/OS and test fixture IDs;
- lint/typecheck/build/component/E2E results;
- accessibility results;
- XSS/security test results;
- loading/error/empty/partial-state coverage;
- known missing API capability and owner decision requested.

## 10. Stop conditions

Stop and mark BLOCKED if:
- CLI/M1 gate not accepted and task is substantial dashboard implementation;
- endpoint or field is absent from approved OpenAPI;
- page requires bypassing backend permission;
- user asks to expose secret or raw private source;
- trust/QA/execution states cannot be represented without ambiguity;
- API lacks safe pagination or evidence authorization;
- only way to show a screen is fabricated data;
- accessibility or XSS testing is skipped for a release-critical view.

## 11. Definition of done

A user can use the web app after M1 to manage an individual or organization workspace, inspect real GitHub-connected projects and customer runners, understand actual run lifecycle and three outcome dimensions, review separate test gates, inspect findings and authorized evidence, verify receipt status and manage roles/integrations without any frontend-authored lifecycle, data source or authorization bypass.
