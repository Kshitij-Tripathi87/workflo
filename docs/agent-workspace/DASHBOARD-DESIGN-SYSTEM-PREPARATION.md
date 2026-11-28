# Dashboard Design-System Preparation — Gemini Workstream

**Status:** design preparation only; no production UI implementation authorized before M1 acceptance  
**Consumer contract:** [M1 API contract freeze](API-CONTRACT-FREEZE-M1.md) after human approval  
**Primary repository area:** `apps/dashboard/`  
**Owner:** Gemini 4 Hydrogen workstream; product owner approves visual direction and semantics.

## 1. Product experience

The dashboard is an engineering control surface for software execution evidence. It must answer, without ambiguity:

1. Which exact repository commit was tested?
2. Where did the run execute, and which runner/runtime image was used?
3. What happened during the run?
4. What did tests establish?
5. Was the environment independently torn down and the receipt verified?
6. What can the current user see or do under their role?

The dashboard is not a marketing landing page, an LLM chat interface or a generic analytics dashboard. Trust evidence and operational state take priority over visual effects.

## 2. Visual direction

**Direction:** restrained technical console; dark neutral foundation; precise typography; high information density with clear hierarchy; thin borders and disciplined accent use.

- Base canvas: deep charcoal/near-black.
- Surfaces: two to three neutral elevation levels; use borders and spacing rather than glass blur.
- Primary accent: cobalt/blue for interactive focus and selected navigation.
- Secondary accent: lime only for a small number of positive/active signals, not decorative highlights.
- No gradients, glassmorphism, glowing blobs, oversized rounded cards, gratuitous 3D or animated background effects.
- Use motion only to clarify state changes (queued → claimed → running) and drawer/dialog transitions.
- Prefer structured tables, timelines, evidence trees and compact status summaries over large decorative cards.

Suggested initial token set (subject to contrast verification in implementation):

| Token | Value | Use |
|---|---|---|
| `--wf-bg` | `#0B0D10` | Main canvas |
| `--wf-surface-1` | `#12161C` | Primary surface |
| `--wf-surface-2` | `#191F27` | Elevated/selected surface |
| `--wf-border` | `#2A333F` | Dividers and controls |
| `--wf-text` | `#E8EDF3` | Primary text |
| `--wf-muted` | `#9AA6B2` | Secondary text |
| `--wf-blue` | `#4B8DFF` | Primary action/focus |
| `--wf-lime` | `#B7E36A` | Limited positive highlight |
| `--wf-success` | `#36B37E` | Verified/passed |
| `--wf-warning` | `#E5A93D` | Degraded/attention |
| `--wf-danger` | `#E05A67` | Denied/failed |
| `--wf-info` | `#64A5D9` | Informational state |

Do not use color as the only status signal. Pair color with a label, icon or explicit text. Validate all text and control combinations against WCAG 2.2 AA before release; values above are starting tokens, not a claim of verified contrast.

## 3. Typography and information hierarchy

- UI/body: Geist Sans or the repository's established sans family; do not introduce multiple competing families.
- Code, commit IDs, digests, run IDs, timestamps and log content: Geist Mono or an established monospace family.
- Use a consistent scale: 12/14/16/20/24/32 px, with line-height chosen for readability rather than visual density alone.
- Page title communicates the current resource, not marketing slogans.
- Section headings describe evidence domains: Execution, QA, Trust, Source, Runner, Evidence.
- Long identifiers wrap safely or truncate with copy/reveal affordance; never silently remove the full value.

## 4. Layout system

- Desktop: 12-column content grid; stable navigation rail; content width adapts to wide log/evidence tables.
- Tablet: 8-column grid; collapsible navigation; tables provide controlled horizontal scrolling.
- Mobile: 4-column grid; preserve critical state, source SHA, run status and trust outcome before secondary metadata.
- Spacing follows a 4 px base unit (4, 8, 12, 16, 24, 32, 48).
- Use square/low-radius geometry by default; reserve larger radii for dialogs and overlay containers.
- Persistent shell: workspace/project context, page navigation, account and runner context.
- Every page must define loading, empty, populated, partial, stale, forbidden and error states.

## 5. Core information architecture

### Navigation
- Overview
- Projects
- Runs
- Runners
- Evidence / Receipts
- Integrations
- Team
- Policies and Privacy
- Audit

Hide or disable sections whose API is not approved or implemented. Do not render empty navigation affordances as if the feature exists.

### Run list
Required columns: status, repository, short commit SHA (copy full SHA), profile, execution outcome, QA verdict, trust status, runner, created time, duration.

Filters: project, status, QA verdict, trust state, time window. Support pagination and URL-persisted query state only where the API contract supports it.

### Run detail
Keep three independent axes visually separate:
- **Execution:** queued, running, completed, infrastructure failure, cancelled/termination pending.
- **QA:** pass, fail, partial, not run.
- **Trust:** verified clean, verification failed, cleanup incomplete, unknown.

Never collapse these into one green/red “run status”. A completed execution can have a failed QA verdict; a passing test can have a failed trust result.

Run detail sections:
1. Source identity: repository, full commit SHA, immutable source digest.
2. Lifecycle timeline: admission, claim, provision, guest ready, test, evidence, teardown, signing.
3. Three outcome panels, each with its own explanation.
4. Runner and runtime identities: runner version, OS/kernel/architecture, Firecracker/jailer version, guest image digest.
5. Test evidence: bounded summary and reports.
6. Teardown evidence: all required host-observed checks, each with timestamp/result.
7. Receipt: DSSE/signature state, signer key fingerprint, receipt digest, offline-verification result and limitations.

### Runner management
Show eligibility, KVM availability, Firecracker/jailer identity, guest image digests, capacity after reservations, heartbeat age, draining/revoked state and supported profiles. Never provide arbitrary remote shell or terminal access.

### Evidence and receipt
Render evidence as an immutable tree with type, digest, byte size, producer identity and authorization to download. Logs are untrusted text: escape them, never execute HTML or embedded script, and apply bounded rendering. Do not show secret-bearing environment variables or raw credentials.

### Team and privacy
Show role and permission clearly. BYOK secrets are write-only; the UI may show provider alias, model ID and last rotation metadata, but never the stored key value. Explain each consent scope and data category before opt-in.

## 6. Shared component inventory for Gemini

Prepare reusable components and variants:
- `AppShell`, `WorkspaceSwitcher`, `ProjectSwitcher`, `SidebarNav`;
- `PageHeader`, `FilterBar`, `DataTable`, `Pagination`;
- `RunStateBadge`, `ExecutionOutcome`, `QaVerdict`, `TrustOutcome`;
- `CommitIdentity`, `DigestField`, `CopyValue`, `Timestamp`;
- `RunTimeline`, `EvidenceTree`, `ReceiptSignaturePanel`;
- `RunnerEligibilityPanel`, `CapacityMeter`, `PolicySummary`;
- `EmptyState`, `ErrorState`, `PermissionDenied`, `Skeleton`, `ConfirmDialog`.

Each component needs a typed prop contract, keyboard behavior, focus state, accessible name and test coverage. Do not create one generic status badge that conflates QA/execution/trust semantics.

## 7. Synthetic prototype dataset

Gemini may use a clearly named, static fixture set for layout work. Use only synthetic values:
- one repository with a fake but format-valid 40-character SHA clearly labelled SYNTHETIC;
- one queued run, one running run, one completed QA-pass/trust-verified run, one completed QA-fail/trust-verified run, one execution failure with trust unknown;
- one eligible and one ineligible runner;
- one evidence manifest with synthetic digests;
- one receipt panel with a fixture signature state.

All prototype views must display a persistent `SYNTHETIC DATA` indicator. Never seed fake records into the real API or present them as product analytics.

## 8. Browser and accessibility acceptance

- Keyboard-only navigation, visible focus, logical focus order and focus restoration.
- Screen reader labels and announcements for changing run state.
- Dialog semantics and escape behavior.
- Responsive layout at mobile, tablet and wide desktop.
- Contrast checks (WCAG 2.2 AA), zoom/reflow and text scaling.
- XSS payloads in repository name, branch, test output, finding text and evidence filename render as inert text.
- Long SHA/digest/log content remains inspectable and copyable.
- Loading, empty, stale, partial, 401, 403, 404, 409, 429 and 5xx states are represented.
- No fake live telemetry; refresh/polling/streaming behavior must match the approved API contract.

## 9. Twenty-five-day M1 boundary

The M1 execution target is 23 December 2026. Gemini's pre-M1 deliverables are limited to the IA, design tokens, component contracts, synthetic prototype and browser/accessibility test plan described in its agent runbook. These outputs run in parallel with the CLI work but do not become dependencies of the CLI, API or Firecracker critical path.

Production dashboard implementation starts only after the human owner signs the M1 acceptance record. The first production slice is read-only: authenticated shell, Runs list, Run detail/timeline, separate Execution/QA/Trust outcomes, and authorized evidence/receipt view. Team, role, analytics, provider settings and runner mutation screens remain later work. The UI must consume generated OpenAPI types and real API states; no endpoint or status may be guessed to accelerate the schedule.

## 10. Explicit implementation gate

Before Milestone 1 is accepted, Gemini may:
- inspect current dashboard shell and dependencies;
- propose information architecture;
- build token/component documentation and static design prototypes using synthetic fixtures;
- write visual regression and accessibility test plans.

Before Milestone 1 is accepted, Gemini must not:
- build production run/runner/evidence screens against guessed API fields;
- introduce mock data that looks live;
- create parallel frontend-only state semantics;
- call runner or guest services directly;
- add a new backend or D1/marketing-site dependency;
- ship dashboard functionality that claims real execution or receipt verification.

After M1 sign-off, Gemini consumes generated types from the approved OpenAPI contract and implements screens incrementally against real API states.
