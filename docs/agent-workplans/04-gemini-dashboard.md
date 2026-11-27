# Agent 04 — Gemini 4 Hydrogen: Dashboard and Product UX

**Role:** Product frontend engineer and browser-workflow specialist  
**Branch:** `agent/gemini-dashboard`  
**Primary owner:** Gemini 4 Hydrogen  
**Reviewers:** GLM (API contract compatibility), GPT-6 Luna (UI/API acceptance), human owner (product decisions)

## 1. Why this model owns this work

Google DeepMind's Gemini 4 Hydrogen model card reports:

- AutomationBench-AA: **76.1**
- OSWorld-2.1 offline subset: **77.6**
- Agents' Last Exam v1.1: **71.6**
- Chartography: **66.6**
- SWE-sweep: **13.5%**
- Terminal-Bench 4.1, cheating-adjusted: **57.0%**

Google lists web development, iterative repository coding/debugging, open-ended agent execution and multimodal knowledge work among its intended uses. The assignment uses the strong automation/computer-use and web-development signals. Its SWE-sweep result is not evidence that it tops general coding benchmarks.

Source: https://deepmind.google/models/model-cards/gemini-4-hydrogen/

## 2. Owned paths

Primary:

- `apps/dashboard/`
- Dashboard-specific tests, fixtures and visual assets.
- Dashboard route/API client modules within the existing Next.js app.

Do not edit:

- `backend/` or `frontend/` (Cortex Autopilot, adjacent product).
- marketing website or Cloudflare Pages Functions.
- control-plane business logic or worker.
- canonical schema files.
- shared API schemas without an approved change.

## 3. Mission

Turn the existing Workflo Next.js shell into a useful operational cockpit that presents real, tenant-scoped execution, QA and trust information. The dashboard is not another execution engine and must not fabricate successful runs.

## 4. Product surfaces and work packages

### GEM-01 — UI audit and information architecture (Days 1–2)

- Inspect `apps/dashboard/` routes, components, styling, auth assumptions and current package scripts.
- Map each screen to the actual control-plane API and schema fields.
- Identify absent endpoints separately from frontend gaps.
- Define loading, empty, denied, error, stale and partial-result states.
- Keep the first navigation small and task-oriented.

**Acceptance:** route map and API dependency table approved before implementation.

### GEM-02 — App shell and design system (Days 3–5)

- Build stable nav, page header, status treatment, accessible dialogs and responsive grid.
- Use Workflo's dark, precise engineering visual identity.
- Establish typography, spacing, status semantics and chart rules.
- Ensure keyboard focus, reduced motion, contrast and screen-reader labels.
- Reuse existing dependencies before adding another UI library.

**Acceptance:** shell passes production build, lint, keyboard and responsive smoke tests.

### GEM-03 — Overview (Days 5–8)

Show real API-derived:

- recent runs;
- active/eligible runners;
- queue/dispatch health where exposed;
- execution/QA/trust breakdown;
- recent trust failures and infrastructure failures.

Do not calculate or display unsupported aggregate metrics. Label missing API capability rather than substituting fixture data.

**Acceptance:** tenant-scoped API fixtures and integration test prove the overview uses real data contracts.

### GEM-04 — Projects and GitHub repositories (Days 7–12)

- Display authorized installations and repositories.
- Connect/disconnect with clear permission scopes.
- Show repository identity and selected default policy.
- Display last connection health and permission expiry/revocation.
- Do not show a project as connected until server confirms it.

**Acceptance:** connect, revoke, insufficient permission, empty installation and unavailable GitHub states tested.

### GEM-05 — Runs list (Days 9–14)

- Search/filter by repository, status, date and outcome where APIs support it.
- Display run ID, attempt, repository, full/short SHA, creation time and three outcome groups.
- Represent infrastructure failure, QA failure, cancellation, incomplete and rejected distinctly.
- Support pagination without fetching unbounded data.

**Acceptance:** canonical status mapping tests; no unknown state rendered as success.

### GEM-06 — Run detail and timeline (Days 12–18)

Display:

- run/attempt ID;
- repository and full commit SHA;
- policy and runtime digests;
- canonical lifecycle timeline;
- execution result;
- QA result and reproducible findings;
- trust verification and teardown outcome;
- evidence references and receipt download/verification state.

Partial evidence must be shown as partial. A test failure with verified execution/teardown is not a platform failure; a successful test with unverified teardown is not a passing trust result.

**Acceptance:** golden records for successful, verified-failing, infrastructure-failed, teardown-failed and attestation-failed runs.

### GEM-07 — Runner management (Days 16–21)

Show registered runners, identity, last heartbeat, KVM eligibility, approved runtime/guest digest, capacity and active attempts. Provide revoke/disable action only if the control-plane API and RBAC authorize it.

Do not expose host shell or arbitrary host configuration in the UI.

**Acceptance:** tenant and role restrictions; stale/offline/unsupported runner states.

### GEM-08 — Receipt and evidence viewer (Days 19–23)

- Show signature verification state and key fingerprint.
- Link receipt claims to evidence references.
- Explain verification failure without implying that signature alone proves software defect absence or data erasure.
- Allow safe download of authorized artifacts.
- Avoid rendering untrusted logs/HTML as active content.

**Acceptance:** invalid signature, missing evidence, tampered receipt, wrong trust key and incomplete teardown have explicit UX states.

### GEM-09 — Settings and integrations (Days 21–25)

- Team members and roles.
- GitHub integration status and scope.
- Privacy mode and inference eligibility.
- Model identity/configuration metadata where authorized.
- Run quotas and API credentials lifecycle.
- Audit event visibility.

Never display model or GitHub secrets. Do not imply hosted inference is enabled when G4/G5 are open.

### GEM-10 — Browser QA and handoff (Days 25–30)

- Validate main journeys in supported browsers/viewports.
- Test keyboard navigation, screen-reader labels, contrast and reduced motion.
- Verify loading, empty, 401/403, 404, 409, 429 and 5xx states.
- Test tenant isolation from the client perspective, while recognizing backend authorization is authoritative.
- Record screenshots only from real or explicitly labeled test fixtures.

## 5. API contract rules

- Consume control-plane APIs only.
- Do not connect directly to runner hosts or guest endpoints.
- Do not connect to marketing website D1.
- Do not hardcode tenant IDs, metrics, runner state or successful run data.
- Use authenticated server-side/session patterns already accepted by the control plane.
- Treat logs and artifact contents as untrusted; escape/sanitize output.
- Respect pagination, timeouts, abort signals and retry-after.
- Do not retry mutations without idempotency support.

## 6. Required tests

- Route and component unit tests.
- API-client schema validation.
- Auth loading/expiry and 401/403.
- Tenant boundary and role gating.
- Empty/loading/partial/error states.
- Lifecycle outcome mapping.
- Pagination and filter behavior.
- Receipt/evidence integrity presentation.
- XSS-safe log rendering.
- Keyboard and responsive browser smoke tests.
- Production build and lint.

## 7. Stop conditions

Do not invent an endpoint to unblock the UI. Record the API gap and request an owner. Do not present mock data as customer data. Do not hide teardown or evidence failures behind a generic green “Success” badge.
