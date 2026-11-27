# Workflo engineering quality gates and enterprise controls

This document defines development/release gates for Workflo. It is a control mapping and implementation plan, not a claim of certification, compliance attestation or independent audit.

## 1. Security invariants

1. Production execution of untrusted customer code uses the approved Firecracker/KVM microVM boundary only, per ADR-0022.
2. Docker and bwrap/namespace profiles are development and CI tools. They are never a strict-production fallback.
3. If the required microVM, jailer, kernel, image, isolation or network controls are unavailable, the worker is ineligible or the run fails with an explicit infrastructure/trust outcome.
4. Signing keys remain outside the guest and ordinary untrusted execution context. Dev signing must be labelled and rejected by production guards.
5. A receipt authenticates signed claims and linked evidence; it does not prove the source is defect-free or that a security boundary worked unless the required evidence validates that claim.
6. Execution, QA verdict and trust outcome are separate dimensions.
7. Guest/model-generated findings are candidates. Only deterministic criteria and host-side verification may promote a finding to verified_failure.
8. Direct cloud inference egress remains frozen until an owner-approved data-flow inventory and fail-closed payload allowlist are proven. Never route source-bearing payloads through an unapproved provider path.
9. Teardown must be independently verified. A cleanup command returning success is not teardown evidence.
10. Unknown, missing or incomplete security evidence must never be upgraded to a pass.

## 2. Mandatory quality gates

### G0 — Scope and baseline
- Clean branch/worktree and exact base SHA.
- Task contract with allowed paths.
- Existing behavior and related tests identified.
- No unapproved source relocation or dependency upgrade.

### G1 — Static and dependency checks
- Python lint/type checks and tests for changed Python packages.
- TypeScript lint/typecheck/build for changed TS packages.
- Dependency lockfile consistency.
- Secret scanning on diff and repository.
- SAST and dependency vulnerability scanning with a documented triage policy.
- License and provenance review for newly added dependencies.

### G2 — Functional tests
- Unit tests for new behavior.
- Integration tests across affected package boundaries.
- Contract/golden-vector tests for shared schemas and canonical JSON.
- CLI compatibility tests for changed commands.
- Regression test for every fixed defect.

### G3 — Security negative paths
- Fail-closed behavior when each required kernel/security primitive is absent or fails.
- Cross-run and cross-tenant reference rejection.
- Denied filesystem/network/process/privilege operations.
- Resource-limit enforcement.
- Malformed, altered and incomplete evidence rejection.
- Signing-key isolation and production dev-key rejection.
- Prompt-injection/untrusted-content handling where agent/tooling code changes.
- No secret or source-bearing payload in blocked egress paths.

### G4 — System integration
- Source revision pinned to exact commit.
- RunSpec/policy digest and environment recorded.
- Guest workload and evidence manifest bound to attempt.
- Teardown and crash recovery exercised.
- Receipt verified independently from the producer.
- Real KVM acceptance is required for Gate B; mocks and non-KVM skips are explicitly non-proof.

### G5 — Release readiness
- All required gates green.
- No unresolved critical/high security findings without explicit risk acceptance.
- SBOM and dependency inventory produced.
- Build provenance and release artifacts bound to immutable commit/digests.
- Fresh-machine installation and rollback/recovery tested.
- User-facing documentation accurately states runtime profile and limitations.

## 3. Enterprise reference mapping

Use the following current published baselines as engineering references. Track future revisions, and record the exact edition used in any audit evidence.

| Reference | Use in Workflo | Engineering evidence |
|---|---|---|
| NIST SP 800-218 SSDF v1.1 (final) | Secure SDLC, security requirements, build protection, vulnerability response | Secure development policy, risk register, review and test records, vulnerability workflow |
| NIST SP 800-218 Rev.1 / SSDF 1.2 (initial public draft) | Monitor and prepare migration; do not describe draft as final | Version-delta note and future adoption task |
| OWASP ASVS 5.0.0 (stable) | Web/API authentication, authorization, input handling, session/security controls | ASVS mapping, test evidence and accepted exceptions |
| SLSA 1.2 (approved specification) | Build/source provenance and artifact integrity | Provenance attestations, builder identity, immutable inputs |
| ISO/IEC 27001:2022 + Amendment 1:2024 | ISMS readiness and organizational controls | Risk treatment, asset inventory, access review, incident/continuity records |
| SOC 2 Trust Services Criteria | Readiness mapping for Security, Availability, Confidentiality as in-scope | Control owner, frequency, evidence, exception, remediation records |
| SPDX or CycloneDX | Software bill of materials | Versioned SBOM tied to release artifact digest |

Reference links:
- NIST SSDF publications: https://csrc.nist.gov/Projects/ssdf/publications
- NIST SSDF project: https://csrc.nist.gov/projects/ssdf
- OWASP ASVS stable release: https://asvs.owasp.org/
- SLSA v1.2: https://slsa.dev/spec/v1.2/
- ISO/IEC 27001:2022: https://www.iso.org/standard/27001
- CycloneDX: https://cyclonedx.org/
- SPDX: https://spdx.dev/

NIST SP 800-218 Rev.1 / v1.2 is an initial public draft in the current NIST publication listing; v1.1 remains the final SSDF baseline. OWASP ASVS stable is 5.0.0, even though its working branch may change. SLSA v1.2 is approved; the next-version draft is not the stable specification.

## 4. Compliance claims

Allowed language during development:
- "Designed with controls mapped to ..."
- "Implementation evidence is being collected against ..."
- "Readiness assessment in progress ..."

Disallowed without independent audit/attestation:
- "SOC 2 certified"
- "ISO 27001 certified"
- "SLSA compliant at level X"
- "Fully compliant"
- "Cryptographically proves the sandbox was secure"

Certification/attestation requires the correct scope, independent assessor/auditor and retained evidence.

## 5. Security-sensitive review policy

The following changes require at least two independent reviews plus human approval:
- sandbox isolation, cgroups, namespaces, Landlock, seccomp, jailer, Firecracker and network enforcement;
- run admission, tenant isolation, authorization, RLS and credential handling;
- signer, key provisioning, receipt generation and verification;
- evidence scope, canonicalization, event chain and policy digest;
- inference egress, data classification and gateway allowlists;
- release signing, provenance and production deployment workflows.

A model may produce threat scenarios and inspect code. Deterministic tests, platform evidence and human review determine acceptance.

## 6. GitHub governance gap

At the audit time, GitHub's branch endpoint reported the main branch as unprotected. This workspace does not change repository settings. Before accepting production work, the owner should configure branch protection/rulesets requiring pull requests, required CI/security checks, stale-review dismissal, restricted force-push/deletion and appropriate bypass controls. Confirm the current setting in GitHub before implementation.

## 7. Per-PR minimum evidence

- Task contract and base/result SHA.
- Changed files and review scope.
- CI check results with exact status.
- Tests executed/passed/failed/skipped.
- Secret/SAST/dependency scan output or explicit workflow links.
- Security negative-path results when relevant.
- SBOM/provenance changes if release/build paths changed.
- Updated documentation and limitations.
