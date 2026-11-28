# Agent 04 — Gemini 4 Hydrogen
## Workflo Dashboard Information Architecture, Design System and Post-M1 Frontend

**Branch:** `agent/gemini-dashboard-frontend`  
**Primary owner:** Gemini  
**Reviewers:** GPT-6 Luna (API contract), GLM (CLI workflow parity), human product owner (UX/security semantics)  
**M1 priority:** bounded design-only track; production frontend is gated by M1 acceptance

## 1. Mission and expected capability fit

**Mission before M1:** prepare a precise design system, information architecture and synthetic prototype so production UI can begin after the actual API and trust semantics are proven.

**Mission after M1:** implement a read-only, evidence-first dashboard against generated OpenAPI types and real API states; only then expand into mutation surfaces.

Routing hypothesis: frontend iteration, visual/browser QA, multimodal design feedback and accessible interaction implementation. Published automation/computer-use benchmarks do not prove visual design quality, accessibility or product correctness. The product owner approves visual direction and semantics.

## 2. M1 restriction

Until the M1 acceptance record is signed:
- design tokens, IA, static components and prototypes with synthetic data are allowed;
- code that consumes live M1 endpoints or claims to show production runs is not allowed;
- no mock records may be seeded into production APIs;
- do not implement screens against guessed Luna endpoints;
- no frontend-only authorization or direct runner/guest calls.

Gemini is not on the M1 CLI/Firecracker critical path. Do not request API changes merely to support a prototype.

## 3. Ownership

**Before M1 acceptance**
- dashboard audit and route inventory;
- dashboard design documentation;
- token definitions and contrast checks;
- static reusable component prototypes;
- synthetic data fixtures with permanent `SYNTHETIC DATA` indication;
- browser/accessibility test plan.

**After M1 acceptance**
- `apps/dashboard/` frontend routes/components/styles/tests;
- generated API-client consumption with Luna coordination;
- browser end-to-end and visual regression tests.

**Never owned**
- FastAPI backend, OpenAPI source, auth/RBAC decisions, DB/RLS, runner services, guest protocol, receipt semantics, source credentials or production data generation.

## 4. Design principles and product semantics

Workflo is an engineering trust console, not a generic analytics dashboard or LLM chat product. Use:
- dark neutral foundation, precise typography, clear hierarchy;
- structured data tables, evidence trees and lifecycle timelines;
- restrained cobalt interaction accent and limited lime positive indicator;
- no gradients, glassmorphism, glowing blobs, giant rounded analytics cards or gratuitous 3D effects;
- motion only when it clarifies a state change;
- status labels in text and icon as well as color;
- explicit unknown/incomplete states.

Always show three separate dimensions:
- **Execution:** queued, claimed, provisioning, running, completed, infrastructure failure, cancellation pending/cancelled.
- **QA:** not run, passed, failed, partial.
- **Trust:** pending, verified clean, verification failed, cleanup incomplete, unknown.

Never reduce these to a single green/red result badge. A completed failed test can still be a correctly signed and trusted execution. A passing QA result with unverified teardown is not a trusted pass.

## 5. Work packages

### GEM-01 — Existing dashboard audit and route map · D1–D2

Inspect `apps/dashboard/`, routing, auth, dependencies, current tests and data flows.

Deliver:
- current route/component inventory;
- existing API use and mock/demo data audit;
- proposed IA and navigation map;
- screen-to-API dependency map (M1 vs post-M1);
- route states for loading, empty, forbidden, partial, stale and failure.

**Acceptance:** exact path inventory, no fake production metrics, design proposal approved by product owner.

### GEM-02 — Design system · D2–D5

Create tokens and usage:
- canvas/surface/border/text/accent/status;
- spacing, grid, typography and mono identifier styles;
- table/filter/form/dialog patterns;
- status and outcome components;
- focus, hover, disabled, loading and error states;
- reduced-motion behavior and responsive breakpoints.

Validate WCAG 2.2 AA contrast; initial colors are not accepted without measured contrast.

**Acceptance:** token spec, contrast report, component API sheet and responsive examples.

### GEM-03 — Run detail semantics and data model prototype · D4–D7

Define source identity, commit/digest display, run/attempt identity, timeline, host/runtime identity, profile, evidence, receipt, signer key and offline verification result.

Use only synthetic values and permanent synthetic-data labeling.

**Acceptance:** prototype reflects M1 interface registry and cannot imply live status.

### GEM-04 — Component library prototype · D6–D12

Prepare static/type-level prototypes for:
- AppShell and navigation;
- PageHeader and filter bar;
- run table;
- ExecutionOutcome, QaVerdict and TrustOutcome;
- CommitIdentity and digest copy controls;
- RunTimeline and EvidenceTree;
- ReceiptSignaturePanel;
- RunnerEligibilityPanel;
- Empty/Error/PermissionDenied/Skeleton/ConfirmDialog.

Each needs typed props, keyboard behavior, focus state, accessible name and component tests. No generic status component that conflates the three outcome axes.

**Acceptance:** component matrix, keyboard/accessibility tests and no network/API side effects in synthetic prototype.

### GEM-05 — Browser and security UX test plan · D10–D16

Specify tests for responsive layout, keyboard navigation, focus return, screen reader state announcements, XSS through logs/branch names/artifact paths, long digests, large timelines, stale data, permissions and 401/403/404/409/429/5xx states.

**Acceptance:** executable browser test plan with test IDs mapped to components and M1 semantics. No arbitrary HTML rendering of logs or artifact content.

### GEM-06 — M1 design handoff · D17–D25

Deliver design files/docs, routes, tokens, component APIs, prototype, synthetic fixtures, API field map, accessibility report and unresolved decisions.

**Acceptance:** DeepSeek/Luna can understand the design constraints without guessing; human owner approves the design direction. This does not count as dashboard implementation.

### GEM-07 — Post-M1 read-only dashboard slice · after signed acceptance only

Implement, in order:
1. authenticated shell and authorized personal project context;
2. Runs list from real API;
3. Run detail and lifecycle timeline;
4. Execution/QA/Trust panels;
5. Evidence/receipt view with authorized download and clear verification claims.

Do not start team management, provider settings, analytics or runner actions before read-only path is accepted.

**Acceptance:** real API only, generated types, server-side authorization, loading/empty/partial/error states, accessibility and browser tests.

## 6. How to work

1. Use the M1 registry for semantics; ask Luna for a contract gap, never invent fields.
2. Keep design and API dependencies visible in a matrix.
3. Make each component independently testable.
4. Use realistic but visibly synthetic fixtures only.
5. Check keyboard-only operation and accessible labels as features are built, not at the end.
6. Provide screenshots or browser recordings for significant flows.
7. Respect reduced-motion preferences and preserve full identifier access.

## 7. Do not

- build a feature-complete dashboard before M1 acceptance;
- add a backend or marketing-site database dependency;
- call runner/guest services directly;
- show synthetic telemetry as real;
- trust org/project IDs in local storage as authorization;
- show secret values;
- render logs/artifacts as executable HTML;
- conflate execution, QA and trust;
- invent statuses, fields, pagination or mutations not in OpenAPI;
- use gradients/glassmorphism/ornamental motion to hide weak hierarchy.

## 8. Completion report

Provide route map, API dependency matrix, design token file, component contracts, responsive/contrast evidence, browser/accessibility test IDs, synthetic fixture manifest, screenshots, unresolved API fields and post-M1 implementation estimate.
