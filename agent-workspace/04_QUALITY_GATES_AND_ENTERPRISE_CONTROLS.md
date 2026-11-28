# Workflo beta quality gates and enterprise controls

## 1. Three independently evaluated testing gates

Every run reports each gate separately. The CLI, API, receipt and GitHub check must preserve this separation.

| Gate | Purpose | Typical contents |
|---|---|---|
| Core | Deterministic functional baseline | Declared tests, build, lint, startup/readiness, API probes and framework profile checks |
| Deep AI | Bounded AI-assisted test discovery and exploration | Coverage-gap analysis, edge-case generation, stateful/API/browser journeys and reproducible regression candidates |
| Security | Deterministic security policy and adversarial checks | Dependency/SAST/secret/config scans, auth/access tests, egress validation, sandbox attack matrix and evidence integrity |

Allowed gate statuses: PASS, FAIL, BLOCKED, SKIPPED, NOT_REQUESTED, ERROR. Each result carries evidence references, start/end time, profile/version and a reason for every non-pass.

Rules:
- A required SKIPPED or NOT_REQUESTED gate cannot result in overall PASS.
- BLOCKED and ERROR are not PASS.
- A passing Core gate cannot hide a failed Security gate.
- Overall QA outcome and trust outcome are separate from process execution status.
- A workflow must never synthesize a single green boolean that obscures these separate states.

## 2. Deep AI testing and finding acceptance

AI-generated tests and findings are hypotheses. Required lifecycle:

candidate → validated plan → bounded execution → reproduction → independent evidence review → accepted finding

A defect report must include exact source SHA, profile, environment, reproduction steps, expected and actual behavior, test artifact, impact and reproduction result. Flaky or non-reproducible results remain observations. A model cannot accept its own finding.

Deep-test agent budgets must be enforced: maximum wall time, tool calls, plan depth, concurrency, memory, output size and artifact size. Every tool is capability-scoped. Browser/API exploration remains inside the guest. No unrestricted host browser or arbitrary shell access.

Security findings with high/critical severity require deterministic evidence where possible and human triage. AI cannot be the security oracle.

Patches are suggestions only. A patch must bind exact bytes, base revision, policy and one-time human approval, and is applied only in a new sandbox. No automatic merge, push or deployment.

## 3. Production isolation and receipt integrity

- Firecracker/KVM per attempt is the only approved production execution boundary under ADR-0022.
- Docker, bwrap, namespaces and plain local runs are development/CI profiles.
- Strict admission fails closed if KVM, jailer, cgroup, network enforcement, artifact verification or teardown prerequisites are absent.
- Every attempt binds immutable RunSpec, exact commit/snapshot digest, policy digest, runtime image digest, runner identity and unique attempt ID.
- Host and guest exchange typed attempt-bound protocol messages only.
- Guest receives no GitHub token, control-plane secret, host filesystem, Docker socket, signing key or runner enrollment private key.
- Host evidence completeness and teardown are independently checked.
- Resource inventory must exist before teardown checks can claim cleanup. Absence of a resource alone is not proof the expected resource was created and removed correctly.
- Receipt fields must describe the operation that actually happened. For example, a host directory deletion cannot be reported as tmpfs unmount. The November 28 change to teardown reporting is a current reminder to test claims against observed mechanisms.
- A receipt signature proves integrity/authenticity of its defined claims, not defect-free software or complete sandbox security.

## 4. Privacy and customer BYOK

- Workflo does not provide API models, hosted model keys or API credits.
- Customer supplies and controls their own provider key.
- Default behavior is local/customer-controlled inference or deterministic non-AI execution.
- Hosted prompt calls are disabled by default.
- Enabling requires explicit consent at workspace and individual run level, with provider/endpoint class, payload schema version and timestamp audited.
- Hosted payloads are strictly typed and allowlisted. Permitted examples may include categorical failure codes, aggregate durations, run/gate statuses and aggregate coverage values.
- Prohibited: source files, diffs, source excerpts, repository archives, stack traces containing source, raw logs, environment variables, secrets, credential values and customer personal data.
- Consent cannot widen the schema. Unknown/free-form fields are rejected.
- If classification is uncertain, block the request.
- Add synthetic canaries and egress tests to prove prohibited data cannot reach the hosted endpoint.
- BYOK secrets are write-only from API, encrypted at rest, masked in UI and logs, rotated/revocable, and never mounted into the guest or included in a coding-agent prompt.

## 5. Identity, individual/team workspaces and authorization

Required account model:
- User and authenticated session.
- Individual workspace.
- Organization/team workspace.
- Workspace membership and invitation lifecycle.
- Project/source connection.
- Runner registration.
- Run, attempt, three gate results, findings, evidence, receipts and audit events.

Proposed roles: Owner, Admin, Developer, Viewer. The action-level permission matrix must be approved before implementation. Never implement simplistic checks such as “role is not Viewer” as the only authorization rule.

Security controls:
- Tenant/workspace context derives from authenticated membership, never caller-supplied workspace ID alone.
- Every tenant-owned row has explicit workspace ownership.
- PostgreSQL RLS is enabled and tested where appropriate; application-layer access checks remain required.
- Runner service identity is separate from human identity.
- Membership removal and role downgrade revoke existing access and force pending jobs to re-check authorization.
- Invitations are scoped, expiring, one-time and auditable.
- No global default organization or cross-tenant resource enumeration.
- Administrative break-glass is disabled by default; any later addition requires strong auth and append-only audit.

Cross-tenant negative tests must cover users, projects, sources, runner registrations, run listing/get/cancel/retry, findings, evidence download, receipt verification and audit export.

## 6. 10–15 concurrent users with multiple runs each

Acceptance scenario:
- 15 authenticated users.
- Each submits three runs in a defined time window: 45 durable run submissions.
- Mix individual and organization workspaces; multiple projects; public and private GitHub repositories.
- Include retry/idempotency replay and duplicate webhook delivery.
- Submit more runs than the configured customer runner slot count to test durable queue and backpressure.
- Restart the control plane while work is queued; restart a runner process during a recoverable attempt.
- Verify no lost, duplicated, cross-tenant or cross-run-misattributed run, event, evidence or receipt.
- Verify fair scheduling, lease expiry, timeout, retry, cancellation races and authorization recheck.
- Record the actual CPU, RAM, disk, runner count and active VM limit used. Do not turn 15 active users into a made-up claim of 15 simultaneous microVMs.

Metrics to capture: API p50/p95/p99 latency, queue age, dispatch delay, throughput, retry count, lease recovery, failure distribution, DB connection saturation, runner CPU/RAM/disk and artifact upload integrity.

## 7. Security acceptance matrix

At minimum:
- Path traversal, symlink escape, hardlink and unsafe archive extraction.
- Process-tree escape, daemon restart, orphan child cleanup and PID/resource exhaustion.
- CPU, memory, disk, process count, wall time, output and artifact-size limits.
- Default-deny networking, DNS rebinding, redirects, IP literals, IPv6, proxy bypass and gateway outage.
- Credentials leaked through environment, command-line args, process listing, logs, temp files or artifacts.
- Runner impersonation, forged assignment, expired/replayed lease and cross-attempt protocol mix-up.
- Cross-tenant object enumeration, stale membership sessions and unauthorized evidence download.
- Tampered receipt, evidence substitution, replay, key confusion and partial evidence bundle.
- Partial teardown, crash recovery and false claims about cleanup mechanism.
- Hosted-prompt consent bypass and source/secret canary leakage.
- Fail-closed strict mode when KVM/jailer/cgroup/network/image requirements are not satisfied.

## 8. Distribution and software supply chain

- Pin toolchains and dependency versions; commit lockfiles.
- Build artifacts from immutable commit/tag and documented builder workflow.
- Generate SBOM and provenance for every distributable.
- Verify binary digest and OS/architecture before execution.
- npm wrapper must refuse unsupported binaries or digest mismatch.
- Clean-machine install/update/uninstall tests for npm, pnpm, Bun and native paths.
- Capture source commit, build identity, dependency inventory, artifact digest and test report.
- Where release signing identities exist, sign and verify artifacts. If no signing identity/notarization is available under the zero-budget constraint, mark packages unsigned and publish checksum/provenance; do not claim notarization or publisher verification.
- Do not publish until owner approval and mandatory gates pass.

## 9. Enterprise-readiness mapping

Use these as control-mapping references, not certification claims:
- NIST SSDF for secure development lifecycle, review and release.
- OWASP ASVS for identity, session, access control, API and logging verification.
- SLSA for build provenance and artifact integrity.
- ISO/IEC 27001 and SOC 2 Trust Services Criteria for evidence organization and audit readiness.

Never claim certification or compliance based only on this plan, a checklist or a passing CI run. Product readiness is defined by demonstrated gate evidence and independent assessment.
