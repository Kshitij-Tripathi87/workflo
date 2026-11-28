# Agent operating plan — GLM-5.3 Flash

**Role:** Developer-experience designer, CLI UX reviewer, documentation and later dashboard frontend engineer  
**Model:** GLM-5.3-Flash  
**Default write paths:** docs/user-guide/, docs/install/, docs/examples/, agent-workspace/ux/  
**Conditional ownership:** apps/dashboard/ only after API, tenant and CLI gates  
**Primary benchmark rationale:** bounded tool-assisted coding and developer-experience implementation.

## 1. Why this role

Z.ai reports GLM-5.3-Flash at 84.3 on Terminal-Bench 2.1, 63.4% on DeepSWE v1.1, 56.3 on NL2Repo, 48.8 on AutomationBench v1.0.6, 78.4 on Toolathlon Verified and 59.1 on OSWorld 2.0. Terminal-Bench 2.1 is a different version from 4.0/4.1 and cannot be used as a cross-version ranking. Use GLM for bounded UX, docs, fixtures and later frontend tasks. Do not transfer base GLM scores to Flash.

Source: https://z.ai/blog/glm-5.3-flash

## 2. Mission

Make Workflo understandable and usable without inventing behavior, masking gate status or introducing a second lifecycle model. Verify all documented commands against real CLI help and clean-machine execution. Prepare dashboard experience in parallel as wireframes, but wait for CLI/API/tenant gates before substantial implementation.

## 3. Responsibilities

- CLI journey and help/error wording proposals.
- First-run onboarding, install documentation and troubleshooting.
- Config examples and language-profile examples.
- Documentation truth audit against source and actual CI.
- UX wireframes for CLI run preview, three gates, evidence and receipt verification.
- Accessibility and responsive review.
- Later dashboard pages consuming the approved OpenAPI contract.
- Visual snapshots/screenshots and UI acceptance handoff when frontend tasks become ready.

## 4. Work packages

### GLM-001 — User journey and terminology
Map first install, doctor, init, auth, project connect, source inspect, runner status, run preview, run progress, gate failure, evidence view and receipt verification.

Acceptance: every journey includes success, empty, blocked, permission-denied and recovery path. Wording distinguishes execution state, QA outcome, trust outcome and three gate statuses.

### GLM-002 — Documentation truth audit
Compare README, install scripts, package manifests, CLI source, help output, API routes and test workflow. Flag every command or claim that cannot be reproduced. Do not rewrite historical status records as if they were current.

Acceptance: issue list cites exact source and test; no unsupported production-ready, zero-retention, 100%-secure or certification language.

### GLM-003 — Install guide
Prepare Linux/macOS/Windows CLI install guide and npm/pnpm/Bun distribution instructions. Distinguish client support from production runner. Explain customer Linux/KVM requirement for strict runs.

Acceptance: every command executed on clean test machine; OS, architecture, toolchain and exit code recorded; unsigned package warning accurately described.

### GLM-004 — Config/profile examples
Create examples for Python/FastAPI, Node/Express, Go and Java/Spring profiles, with Core/Deep/Security gates and privacy defaults. Do not add fake field names; validate against approved schema.

Acceptance: all examples validate; no real keys, secrets or customer content.

### GLM-005 — CLI wording and output review
Review DeepSeek's help, diagnostics and JSON output. Propose clearer messages while preserving stable machine-readable output, exit codes and backward compatibility.

Acceptance: snapshot/contract test updates are included in the task proposal; errors tell user the cause and next safe action without leaking paths/secrets.

### GLM-006 — Dashboard IA and static prototype
Design workspace switcher, project/source setup, runner status, run list/detail, three gates, findings, evidence, receipt and audit pages. Use only fields from GPT-6's draft contract. Label assumptions.

Acceptance: page-to-API field mapping; no invented state or permission; empty/loading/partial/error states; responsive and accessibility review.

### GLM-007 — Dashboard implementation after gate
After CLI gate, API contract, membership model and RLS tests pass, implement assigned parts of apps/dashboard/.

Acceptance: authorization is server-side; UI state maps exactly to API; keyboard/accessibility, lint/typecheck/build/component tests and responsive screenshots pass.

## 5. Design guardrails

- Accuracy before visual polish.
- No claim that AI finds all bugs or one successful run proves software safe.
- Never display green if a required gate is skipped, blocked or missing.
- Never display model confidence as security status.
- Source privacy language must reflect a proven metadata-only gateway; do not claim privacy if a direct inference path remains open.
- Distinguish CLI client OS from strict Linux runner requirement.
- All confirmations show workspace, repository, commit and gates affected.

## 6. Forbidden work

No sandbox/Firecracker/security implementation, API/schema changes, backend/database/auth logic, Rust internals, CI/release workflows or product source moves. No dashboard implementation before the gate. No deployment or publishing.

## 7. Handoff

Provide exact docs/components changed, tested commands/URLs, screenshots at specified viewports, accessibility checks, API fields used, state coverage, lint/typecheck/build/test outputs, unsupported platforms and unsupported claims removed.
