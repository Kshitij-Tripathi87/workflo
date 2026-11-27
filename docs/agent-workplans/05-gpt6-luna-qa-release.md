# Agent 05 — GPT-6 Luna: Cross-System QA, CI and Release Evidence

**Role:** Integration test engineer and release assurance analyst  
**Branch:** `agent/gpt6-luna-qa-release`  
**Primary owner:** GPT-6 Luna  
**Reviewers:** relevant subsystem owner for each test, human release owner for go/no-go

## 1. Why this model owns this work

OpenAI reports GPT-6 Luna at **66.6% on DeepSWE v1.1 at max effort**, describing performance as comparable to its compared Opus 5/Fable 5 medium-effort results at materially lower per-task cost. DeepSWE is a long-horizon software-engineering benchmark on real codebases.

Source: https://openai.com/index/introducing-gpt-6-sol-and-luna/

This supports using Luna for sustained test implementation, regression investigation, contract tracing and release evidence preparation. It does **not** make Luna an independent security authority or allow it to approve its own changes.

## 2. Owned paths

Primary:

- Cross-system test suites in the agreed test locations.
- `.github/workflows/` for CI, security and release evidence automation.
- Release runbooks and acceptance reports under `docs/release/` (create only if required and approved).
- Agent coordination/test traceability artifacts under `docs/agent-workplans/` through PRs.

Do not modify implementation paths owned by other agents. If a defect is found, provide a minimal reproducer and open a focused issue/PR request for the owning agent.

## 3. Mission

Create an evidence-backed acceptance system that verifies the assembled product across the CLI, control plane, customer runner, Firecracker guest, inference policy, receipt verifier and dashboard.

The testing function must distinguish real tests from mocks, skipped checks, scripted demonstrations and unproven claims.

## 4. Work packages

### LUNA-01 — Requirements-to-evidence matrix (Days 1–3)

For each launch requirement, record:

- requirement ID;
- source (ADR, product boundary, privacy promise, release acceptance);
- owner;
- implementation path;
- positive test;
- negative test;
- real-environment evidence required;
- current status;
- release gate.

Use states: `NOT_STARTED`, `IMPLEMENTED_UNVERIFIED`, `MOCK_TESTED`, `INTEGRATION_TESTED`, `REAL_GATE_PASSED`, `BLOCKED`. Never collapse them into one green status.

**Acceptance:** every G0–G8 gate has traceable tests and an owner.

### LUNA-02 — Contract and schema regression suite (Days 3–7)

- Check Pydantic model exports against generated JSON Schema.
- Check TypeScript mirrors/golden fixtures against canonical Python schema.
- Exercise legal/illegal lifecycle transitions.
- Test execution, QA and trust outcome distinctions.
- Preserve legacy receipt verification compatibility.
- Test tamper detection and trusted-key handling.
- Verify canonical JSON/digest vectors.

**Acceptance:** schema export, parity and transition tests execute in CI; no silent skips.

### LUNA-03 — CLI-to-control-plane E2E harness (Days 5–10)

Test:

- clean CLI install;
- authentication and token expiry;
- local and GitHub repository identity;
- full commit SHA pinning;
- idempotency;
- admission/rejection;
- status and cancellation;
- offline receipt verification.

Prefer deterministic fixtures; use real API integration on a controlled staging environment for the end-to-end acceptance.

**Acceptance:** reproducible test report with exact CLI build and control-plane commit.

### LUNA-04 — Runner and Firecracker acceptance harness (Days 7–16)

Coordinate with DeepSeek. Turn every Gate B requirement into a real-KVM scenario. Separate:

- unit/mock;
- host integration;
- real KVM boot;
- adversarial KVM;
- teardown verification.

A test that skips because /dev/kvm or artifacts are unavailable is a non-proof. The workflow must fail the release job if required real KVM evidence was not produced.

**Acceptance:** a protected KVM run proves boot, workload, isolation, limits, egress, crash and teardown on an exact commit and pinned images.

### LUNA-05 — Tenant and control-plane resilience (Days 10–17)

- Real PostgreSQL RLS using a non-owner/non-superuser role without BYPASSRLS.
- Cross-tenant read/write/artifact denial.
- Outbox replay and idempotency.
- Duplicate runner claim.
- Heartbeat/lease expiry.
- Dispatcher restart/recovery.
- Cancellation-vs-completion race.
- DB outage and partial evidence upload.

**Acceptance:** no test uses database-owner bypass as a substitute for customer role enforcement.

### LUNA-06 — Privacy and model adversarial suite (Days 13–20)

Coordinate with MiniMax. Verify actual outbound payloads in controlled staging. Test raw source, secrets, logs, stack traces, prompt injection, model-generated unknown tools, malformed schemas, quotas, timeouts and gateway outages.

- Capture only synthetic fixtures.
- Ensure test reports do not retain actual secret bytes or customer source.
- Validate direct inference routes are unreachable in strict mode.
- Confirm model/provider outage does not change privacy mode or trigger fallback.

**Acceptance:** outbound payload assertions and negative tests pass on the actual gateway path; mocks alone are insufficient.

### LUNA-07 — Dashboard/API acceptance (Days 16–22)

Coordinate with Gemini. Test real run state mapping, tenant isolation, role restrictions, stale runner state, artifact authorization and safe log rendering.

**Acceptance:** critical user journeys work against the staging control plane and display real states, including failures.

### LUNA-08 — CI and release pipeline (Days 18–25)

- Keep lint, typecheck, unit and component tests.
- Add integration and contract parity gates.
- Add non-skipping KVM Gate B workflow on protected KVM runner.
- Add P4 real model artifact and protected staging workflow without bypass.
- Add PostgreSQL RLS and tenant isolation gate.
- Add secret/dependency/SBOM/build provenance checks.
- Upload diagnostics even on partial failure, with redaction.
- Pin GitHub Actions by full commit SHA where required by repository policy.
- Prevent concurrent release workflows from reusing the same protected model/runner state.

**Acceptance:** PR and release workflows clearly distinguish fast CI from real production-readiness gates.

### LUNA-09 — Chaos and performance test plan (Days 20–27)

Build bounded tests for:

- runner kill/restart;
- Firecracker crash;
- guest kernel failure;
- network partition;
- control-plane/API restart;
- DB outage;
- disk full;
- model timeout/429/5xx;
- interrupted evidence upload;
- teardown uncertainty;
- concurrency 1/2/4 and staged load increases.

Record measured run duration, provisioning time, queue wait, peak memory/CPU, error class and evidence completeness. Do not publish synthetic benchmark values as observed results.

### LUNA-10 — Beta release evidence (Days 26–30)

Produce:

- exact release commit and image/model digests;
- test execution counts, pass/fail/skip totals;
- real KVM Gate B evidence index;
- model Gate 4/5 evidence if enabled;
- database RLS/tenant evidence;
- SBOM and build provenance;
- clean-install and update/rollback report;
- open-risk register;
- incident/rollback runbook;
- go/no-go recommendation.

The human owner makes the final release decision.

## 5. Failure classification

Use distinct classes:

- `POLICY_REJECTED`
- `AUTHORIZATION_FAILED`
- `INFRASTRUCTURE_FAILED`
- `EXECUTION_FAILED`
- `QA_FAILED` / verified test failure
- `TEARDOWN_FAILED`
- `ATTESTATION_FAILED`
- `CANCELLED`
- `INCOMPLETE`

A failure must retain enough redacted evidence to diagnose it, but not raw secrets or arbitrary source.

## 6. Test quality rules

- Assert observable outcomes, not implementation details.
- Include both positive and negative tests.
- Avoid tests that pass when the security mechanism is skipped.
- Use independent verification for signed receipts and teardown.
- Use deterministic fixtures and pinned dependencies.
- Separate mocks from real infrastructure tests in reports.
- Do not allow snapshot/golden updates to normalize a security regression.
- A passing test suite is evidence for tested behavior only, not proof of all possible security.

## 7. Stop conditions

Do not recommend launch when a critical/high trust-boundary finding remains open, a required real gate is skipped, evidence is missing/tampered, tenant isolation is unproven, hosted payload inspection is absent or release artifacts are mutable/unpinned.

Do not close another agent's work based only on its completion message. Reproduce the behavior independently.
