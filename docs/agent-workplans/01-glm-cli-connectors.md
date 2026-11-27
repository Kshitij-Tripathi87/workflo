# Agent 01 — GLM-5.3-Flash: CLI and Connector Workstream

**Role:** CLI/integration engineer  
**Repository:** `Kshitij-Tripathi87/workflo`  
**Branch:** `agent/glm-cli-connectors`  
**Primary plan owner:** GLM-5.3-Flash  
**Reviewers:** DeepSeek (server protocol), GPT-6 Luna (acceptance), human owner (shared contracts)

## 1. Why this model owns this work

Z.ai's GLM-5.3-Flash announcement reports:

- Terminal Bench 2.1: **84.3**
- Toolathlon Verified: **78.4**
- DeepSWE v1.1: **63.4**
- AutomationBench v1.0.6: **48.8**

These published results suggest useful tool-use, terminal workflow and multi-step integration strengths. They are not directly comparable with newer Terminal-Bench 4.0/4.1 scores from other model labs. The assignment is therefore CLI orchestration and connector integration, not high-risk runtime authority.

Source: https://z.ai/blog/glm-5.3-flash

## 2. Owned paths

Primary:

- `apps/workflo-cli/`
- CLI tests under `apps/workflo-cli/tests/`
- CLI-specific source acquisition and connector client modules within the existing package layout
- CLI installer/update scripts only when necessary and coordinated

Do not edit:

- `worker/`
- Firecracker host manager
- `apps/dashboard/`
- inference gateway/model implementation
- canonical schemas without approval
- marketing website or Cloudflare Pages backend
- adjacent Cortex `backend/` and `frontend/`

## 3. Mission

Deliver a reliable CLI workflow from local/GitHub source selection through run admission, status inspection and offline receipt verification. Keep the CLI thin: orchestration and operator UX belong in the CLI; execution and authorization remain on the control plane/runner.

## 4. Work packages

### GLM-01 — Baseline audit (Days 1–2)

- Read README, PRODUCT_BOUNDARIES, Phase 0 reconciliation, ADR-0022 and current CLI package.
- Inventory commands, flags, exit codes, config locations, auth, local/remote execution paths and tests.
- Identify old paths and behaviors that must remain compatible.
- Record bugs separately from desired UX changes.

**Acceptance:** an implementation map with file references, current tests and prioritized gaps; no mass rewrite.

### GLM-02 — Configuration and initialization (Days 3–5)

- Improve `workflo init` project discovery and generated configuration.
- Reconcile existing `workflo.yaml` and `~/.config/workflo/config.json` behavior before adding any new path.
- Keep config parsing strict; reject unknown keys and invalid values.
- Ensure secrets are stored in OS credential storage where available, with the existing restricted fallback behavior.
- Redact credentials from all CLI output and diagnostics.

**Acceptance:** tests for missing, malformed, oversized, unknown-key and secret-bearing configurations; no config-path collision.

### GLM-03 — Doctor and strict-profile UX (Days 4–6)

- Report OS, Python, Git, KVM, Firecracker/jailer, image digests, cgroups, network controls and runner eligibility accurately.
- Distinguish a development environment from a strict production-eligible runner.
- Never label bubblewrap/Docker as the production microVM boundary.
- Return actionable remediation without silently installing privileged dependencies.

**Acceptance:** absent KVM or unapproved image produces an explicit ineligible result; development mode is clearly labeled.

### GLM-04 — Source pinning and repository acquisition (Days 5–9)

- Support local path and GitHub repository input using approved connector contracts.
- Resolve symbolic refs to immutable full commit SHA before admission.
- Bind repository identity, full commit SHA, policy digest and run request ID.
- Reject unresolved refs, ambiguous revisions, unsupported transport and oversized source.
- Do not place GitHub installation tokens in guest environment, logs, receipts or CLI config.
- Coordinate source acquisition protocol with DeepSeek.

**Acceptance:** branch-movement test proves the admitted run still uses the selected full SHA; token-scrubbing test passes.

### GLM-05 — GitHub connector client flow (Days 6–11)

- Implement CLI-side GitHub connection UX against the agreed GitHub App/control-plane API.
- Support listing authorized installations/repositories and choosing a repository.
- Handle expired/revoked/insufficient permissions clearly.
- Deduplicate webhook-driven state from the client perspective; the server remains the webhook authority.
- Publish check status only through the control-plane API and only when the granted installation scope allows it.

**Acceptance:** public/private repo happy path, revoked installation, insufficient permission, expired token and unavailable provider tests.

### GLM-06 — Run lifecycle commands (Days 9–14)

- Make `workflo run` submit a versioned request and idempotency key.
- Display admission/rejection distinctly from execution.
- Make `status` read canonical lifecycle state without inventing local state.
- Implement cancel/status timeout handling and safe retry rules.
- Preserve separate Execution, QA and Trust results.

**Acceptance:** duplicate submission does not create duplicate admitted work; cancellation races are surfaced accurately.

### GLM-07 — Receipt and output UX (Days 12–16)

- Improve `verify`, `inspect` and `explain`.
- Display signing identity/fingerprint, receipt version, run/attempt, source SHA, policy/runtime digests, evidence references and three outcome categories.
- Distinguish invalid signature, unknown trust key, missing evidence, tampering, incomplete teardown and verified QA failure.
- Provide stable JSON output and stable exit codes for CI consumers.

**Acceptance:** golden receipt matrix covers valid, altered, missing, wrong-key, incomplete-evidence and teardown-failed cases.

### GLM-08 — Installation and update reliability (Days 17–21)

- Verify clean install and upgrade on the officially supported OS/Python matrix.
- Verify package integrity and pinned dependency resolution.
- Produce a safe rollback path.
- Prevent update during active execution or explain that it must wait.
- Ensure update cannot run arbitrary unverified downloaded code.

**Acceptance:** clean-machine install -> run -> verify, upgrade -> rollback and uninstall tests.

### GLM-09 — Polish and integration (Days 22–27)

- Improve progress display, error classification and non-interactive mode.
- Validate stdout/stderr behavior and JSON mode.
- Ensure no secrets/source content appears in diagnostics.
- Resolve integration issues reported by GPT-6 Luna.

**Acceptance:** CLI smoke suite passes on clean Linux and supported developer platforms.

### GLM-10 — Handoff (Days 28–30)

Deliver CLI command reference, compatibility list, supported platform table, installation notes, known limitations, tests and tagged beta candidate.

## 5. API and contract rules

- Consume schemas exported by `packages/workflo-schema`; do not duplicate lifecycle enums in Click commands.
- Treat the control plane as authority for run IDs, admission, attempt status and cancellation.
- Send idempotency keys on mutating requests.
- Do not trust client-supplied tenant identity or repository permissions.
- All request payloads must be versioned and size-limited.
- Preserve compatibility for previously issued receipts.

## 6. Required tests

- CLI command and argument parsing.
- Config permission/redaction.
- Local path traversal and symlink policy.
- Git ref -> immutable SHA resolution.
- Authentication expiry/revocation.
- GitHub private repo scope and token expiry.
- Idempotency and duplicate submission.
- Cancellation/timeout/retry semantics.
- JSON output and exit-code contract.
- Offline receipt verification.
- Clean install/update/rollback.
- No source or secrets in telemetry.

## 7. Handoff format

Each PR must state plan IDs, exact file ownership, test commands/results, screenshots or terminal transcript where helpful, any API change, security impact, limitations and the base commit SHA.

## 8. Stop conditions

Stop and request a human decision if the work requires:

- a change to canonical lifecycle/receipt semantics;
- broader GitHub App permissions than read metadata/contents plus narrowly justified Checks write;
- a direct execution path around the control plane;
- passing source or provider credentials into the guest;
- changing strict-mode fallback behavior.

A CLI feature is not done because a mocked command returned success; it must be tested against the actual control-plane contract.
