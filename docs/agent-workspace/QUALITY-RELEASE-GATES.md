# Workflo Quality, Security and Release Acceptance Programme

## 1. Evidence states

Every requirement/test must use one of these states:

- NOT_STARTED
- IMPLEMENTED_UNVERIFIED
- MOCK_TESTED
- INTEGRATION_TESTED
- REAL_ENVIRONMENT_TESTED
- ACCEPTED

A skipped test is NOT_PROVEN, never passed. A mocked Firecracker or mocked provider test cannot satisfy a real KVM or outbound privacy gate.

## 2. CLI installation acceptance

Matrix to test:
- npm global install
- pnpm global install
- Bun global install
- direct Linux archive/package
- macOS Apple Silicon and Intel archive/package
- Windows x64 archive/installer
- supported Linux x64/ARM64 runner binaries

For each:
- install from clean machine/container/VM;
- workflo --help and --version;
- checksum/signature/provenance validation;
- upgrade one prior version to new version;
- rollback to prior version;
- uninstall leaves no active service/credential residue;
- reinstall works;
- no Python runtime requirement for Go CLI;
- no install-time secret prompts;
- PATH and quoting work under relevant shells;
- proxy/offline/partial download errors are actionable;
- update does not replace a running binary;
- package names and OS/CPU optional dependencies resolve correctly in npm, pnpm and Bun.

## 3. Core CLI functional acceptance

- init detects without executing untrusted project code.
- doctor reports exact client and runner eligibility separately.
- auth login/refresh/logout/revoke.
- individual and organization context.
- GitHub installation/repository scope.
- local path validation.
- immutable source SHA.
- policy and profile validation before submission.
- dry-run does not create a sandbox.
- idempotent run submission.
- status, logs and cancellation.
- JSON output and stable exit contract.
- receipt verification offline.
- clear distinction between execution, QA and trust.

## 4. Connector acceptance

GitHub:
- public repo.
- private repo in selected installation.
- repository not included in installation.
- installation revoked/removed.
- token expired between acquisition and clone.
- branch moves after run submission; run uses selected full SHA.
- webhook signature invalid.
- webhook replay/duplicate delivery.
- PR check publication permission missing.
- PR check result is bound to repository, commit SHA and run ID.
- no contents-write permission requested.
- no token in CLI logs, guest environment, receipt or source artifact.

Local:
- valid repo.
- missing Git metadata.
- uncommitted changes policy (must snapshot/hash and clearly identify working-tree vs commit identity).
- submodule/LFS policy.
- symlink/path traversal tests.
- very large repository and file-count limit.
- nested .git and ignored/hidden files.
- secret file exclusion/handling.
- source manifest and digest reproducibility.

## 5. Firecracker Gate B

This is a real release gate and remains governed by ADR-0022.

Required evidence:
- KVM-capable host and accessible /dev/kvm.
- pinned Firecracker/jailer binary identities.
- approved immutable guest kernel/rootfs hashes.
- real boot and guest supervisor handshake.
- one fresh VM per run attempt.
- host API operations only from approved typed list.
- no generic shell/Docker socket/host filesystem operation.
- bounded CPU/memory/disk/PID/output/time.
- egress deny-by-default and metadata IP protection.
- DNS and internal service scope enforced.
- cross-VM separation.
- host crash, guest crash and VMM kill behavior.
- lease loss and duplicate claim behavior.
- cancellation and force terminate.
- independent teardown checks of VMM, jailer, cgroup, namespace, network, disk/workspace and vsock/listener.
- teardown failure prevents verified trust receipt.
- evidence is retained and independently checked.

The KVM host integration must actually run. If no eligible runner or artifacts exist, Gate B is blocked—not simulated as passed.

## 6. Language and framework acceptance

For each language profile, test:
- minimal project passes;
- deterministic failing test is reported as QA failure;
- dependency preparation runs under restricted profile;
- lockfile/toolchain pin respected;
- test command is exact argv and runs only in guest;
- test timeout;
- dependency fetch failure;
- malformed test report;
- huge output;
- unexpected network;
- application startup/readiness if app exploration is enabled;
- artifacts and evidence match the exact commit.

Profiles:
- Python + pytest; FastAPI/Flask/Django app profile where explicit.
- Node.js + npm/pnpm/Bun; Express/Next.js profile; Playwright only when pinned.
- Go + go test ./....
- Java + Maven/Gradle.
No arbitrary dependency or tool version may be pulled into the sealed stage.

## 7. Sandbox adversarial acceptance

Use controlled synthetic fixtures and authorized test infrastructure only.

- host filesystem access denied;
- privilege and namespace boundary enforced;
- Docker socket unavailable;
- host networking denied;
- cloud metadata endpoints blocked;
- cross-VM probes denied;
- resource exhaustion is bounded;
- PID/process explosion is bounded;
- disk fills and output caps handled;
- guest attempts unknown host protocol operation;
- malformed/oversized/replayed vsock messages rejected;
- stale/expired capability rejected;
- malicious repository setup/config does not run on host;
- symlink and path traversal rejected;
- test process attempts to persist outside ephemeral disk;
- guest crash and host crash leave no false clean result.

No arbitrary third-party targets. Test only fixtures and systems for which Workflo has authorization.

## 8. BYOK and privacy acceptance

- provider keys stored in OS vault/local customer secret store, not in CLI config or guest.
- no provider credential in RunSpec, logs, event, receipt, environment or dashboard.
- explicit org/project consent and per-run consent required for hosted metadata.
- no consent -> no hosted request.
- source/file content rejected.
- raw logs rejected.
- raw request/response body rejected.
- secrets, API keys, cookies, authorization headers and env variables rejected.
- arbitrary caller-supplied prompt rejected; gateway constructs prompt.
- allowlisted schema version and fields required.
- size/depth/token/call/time/cost caps.
- provider origin allowlist and TLS verification.
- provider output schema and tool arguments validated.
- provider timeout/429/5xx does not trigger direct or alternate-provider fallback.
- test actual serialized outbound payload against synthetic fixtures.
- logs capture metadata only; do not retain secret/source bytes.

BYOK does not grant permission to send source code. Provider terms/retention are displayed and accepted by the customer.

## 9. AI agent/tool safety acceptance

- prompt injection in README, issue text, code comments, logs and HTTP output.
- model suggests unknown tool.
- malformed/extra arguments.
- path traversal and out-of-root path.
- cross-run and cross-tenant references.
- arbitrary HTTP target.
- excessive tool-call loops.
- unbounded response tokens.
- repeated non-idempotent action.
- model asks to modify its own permission.
- generated tests attempt to overwrite source.
- model output contains secret-like text.
- tool gateway unavailable.

The deterministic policy engine authorizes each action. Model text is never treated as permission.

## 10. Backend/tenancy acceptance

- Individual workspace.
- Organization creation and invitation.
- Owner/Admin/Developer/Viewer role matrix.
- user A cannot read org B.
- project A cannot reference runner B without permission.
- direct ID guessing cannot bypass authorization.
- PostgreSQL RLS using non-owner/non-superuser role without BYPASSRLS.
- forced row-level security on tenant tables where feasible.
- connection-pool context cannot bleed between tenants.
- API rate limits and quotas.
- duplicate idempotency key.
- outbox atomicity.
- dispatcher restart and lease recovery.
- runner certificate revocation.
- pagination and bounded response.
- audit log authorization.
- deletion/retention behavior.
- database backup and restore drill.

## 11. Scale and load test

Controlled scenario:
- 15 concurrent user sessions;
- 3 run submissions each (45 total);
- 2 or more organizations;
- multiple projects;
- uneven burst distribution;
- duplicate/retried POSTs;
- runner pools with constrained capacity;
- one runner taken offline;
- one runner lease expires;
- one provider returns 429/timeout;
- one run cancelled during provisioning;
- one run cancelled during execution;
- dashboard polls while the load occurs.

Measure:
- auth and API latency;
- run admission latency;
- queue wait;
- dispatch/claim latency;
- runner utilization;
- VM provision latency;
- execution duration;
- cancellation-to-verified-termination latency;
- evidence upload/verification duration;
- DB connection/pool saturation;
- outbox age and retry count;
- memory/CPU/disk/network;
- provider token/cost usage;
- error class and retry count.

Initial service-level objectives are proposals, not advertised claims:
- zero lost committed dispatch intents in fault tests;
- no duplicate active execution for a single attempt;
- no cross-tenant data access;
- no over-reservation of runner resources;
- admission API p95 target under 1 second on the reference control-plane environment;
- status polling p95 target under 1 second at the target test load;
- queue waiting is visible and cancellable;
- 100% of completed receipts in the acceptance set independently verify or are explicitly classified as invalid/incomplete.

If the environment cannot meet a latency target, report the measurement, hardware and load shape; do not hide it.

## 12. CI and supply-chain gates

- Go fmt/vet/staticcheck and unit tests.
- Python lint/typecheck/test compatibility suites.
- Node/TypeScript lint/typecheck/build.
- schema export/parity and contract golden tests.
- dependency/vulnerability scan.
- secret scanning.
- SBOM for CLI, runner and guest image.
- image and binary digest verification.
- pinned GitHub Actions by full commit SHA where policy requires.
- release artifact provenance/attestation.
- clean-room install test.
- no security workflow weakened or skipped.
- KVM workflow required for strict release.
- model/BYOK outbound payload workflow required if AI feature enabled.

## 13. Beta go/no-go

Launch only when:
- native CLI packages work on every claimed OS/architecture;
- GitHub private repository and PR-check flows pass;
- runner and Firecracker Gate B pass on real KVM;
- four language profiles pass their representative matrices;
- core/deep/security stages have honest independent statuses;
- BYOK privacy and consent gate passes;
- backend tenant/RLS and 15-user/45-submission tests pass;
- dashboard displays actual results after CLI gate;
- no unresolved critical/high security or privacy finding;
- release binary, guest image and protocol digests are pinned;
- rollback, support and incident runbooks exist.

No fixed date overrides a failed release gate.
