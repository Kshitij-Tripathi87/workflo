# Milestone 1 — Native CLI → Firecracker/KVM → independently verified receipt

**Status:** Engineering acceptance specification · 2026-11-28  
**Priority:** P0 — first implementation milestone  
**Owner:** DeepSeek (implementation), MiniMax (security test owner), GPT-6 Luna (API/protocol contract), human owner (architecture/security acceptance)

## 1. Exit outcome

A user submits an exact GitHub commit through the native Go `workflo` CLI. A customer-controlled, eligible Linux KVM runner obtains that exact revision, provisions a fresh Firecracker microVM for the attempt, executes one pinned deterministic test profile, collects bounded evidence, shuts down the VM, independently verifies that host resources were removed, and emits a signed receipt. The CLI then verifies the receipt and evidence offline using an explicit trust anchor.

This is the first real milestone. A working CLI help screen, mock VM, green unit tests, five agent plans or a dashboard prototype do not satisfy it.

## 2. Scope — deliberately narrow

### Included
- Go `workflo` CLI with `--version`, `doctor`, `run` and `verify` for the vertical slice.
- One customer-controlled Linux x86_64 KVM runner.
- Existing FastAPI control plane and durable dispatch path where usable; keep it colocated/self-hosted for the no-hosted-infrastructure development path.
- Exact GitHub commit resolution and source digest verification.
- One pinned guest kernel/rootfs and one Firecracker/jailer version.
- One deterministic Python + pytest profile first; no app discovery or browser exploration.
- Fresh microVM per attempt; no VM reuse.
- Bounded stdout/stderr, test report and evidence manifest.
- Independent host-side teardown verification.
- Signed receipt and offline verifier.
- Real KVM evidence with pinned artifact and source digests.

### Explicitly excluded from this milestone
- Dashboard feature implementation.
- Multi-agent or hosted LLM inference.
- Deep AI testing and security testing stages.
- All four language profiles.
- Windows/macOS strict runner support.
- Hosted Workflo execution infrastructure.
- npm/pnpm/Bun public publishing and native installer release.
- Automatic patching, merge or deployment.
- Treating Docker, bwrap, namespaces-only or host execution as strict isolation.

A local/dev runner may be used for developer iteration, but its outputs must carry a non-production runtime type and must never satisfy this gate.

## 3. Required sequence

1. **CLI preflight:** parse and validate arguments; reject conflicting flags; confirm runner eligibility. No source command is executed on the user's host.
2. **Immutable source selection:** resolve the requested ref to a full commit SHA; display it before admission; bind repository identity + SHA into RunSpec. A moving branch must not change the admitted commit.
3. **Admission:** authenticate, authorize repository/project/runner, check policy and capacity, and create Run + RunAttempt + DispatchOutbox atomically with idempotency.
4. **Runner claim:** authenticated runner claims a lease; assignment is signed, attempt-bound, expiring, and includes policy, image digests, resource ceilings, network policy and typed capabilities.
5. **Source acquisition:** runner obtains only the selected commit. GitHub installation credentials remain host-side, short-lived and repository-scoped. They are removed before guest start and never enter the guest, receipt or logs.
6. **Source integrity:** create a canonical source inventory and digest; enforce file-count, total-byte, per-file, path, symlink, submodule and LFS policy. The VM receives an immutable source artifact, not a host working-tree mount.
7. **Provision:** validate pinned Firecracker/jailer/kernel/rootfs identities and host eligibility. Start one fresh microVM with a fresh writable disk, bounded vCPU/RAM/disk/PID/time/output, deny-by-default egress and typed vsock.
8. **Guest handshake:** authenticate run/attempt/sandbox identity, policy digest, nonce and protocol version. Reject unknown, oversized, replayed, stale or cross-attempt messages.
9. **Test:** execute only the pinned profile's structured argv inside the guest. The host never interpolates repository-controlled command text into a shell command.
10. **Evidence:** collect the test report, bounded output, source manifest digest, runtime/image digests, policy digest, lifecycle timestamps and evidence hashes. A test failure is a QA failure, not automatically an infrastructure or trust failure.
11. **Teardown:** request graceful guest shutdown; force terminate within a bounded deadline; independently probe VMM, jailer, cgroup, namespace, network device/rules, disk/workspace, vsock/listener and temporary credential removal.
12. **Receipt:** only the trusted host verifier may authorize signing. Any missing/unknown/incomplete teardown evidence prevents a verified-clean trust outcome. Receipt binds repository, full SHA, source digest, run, attempt, sandbox, policy, runtime, evidence root, outcomes and signer identity.
13. **Offline verification:** copy receipt, evidence bundle and trust anchor to a clean machine with network disabled. Verify signature, trusted key, canonical encoding, evidence hashes, repository/full-SHA/source binding, policy/runtime/attempt binding and lifecycle semantics.
14. **Reproducibility:** rerun from a clean checkout and reproduce the same source/policy/runtime binding (timestamps and nondeterministic execution fields may differ).

## 4. CLI acceptance contract

Minimum invocation:

```bash
workflo doctor
workflo run \
  --repo https://github.com/OWNER/REPO \
  --ref FULL_40_CHARACTER_COMMIT_SHA \
  --profile python-pytest@PINNED_VERSION \
  --test \
  --runner RUNNER_ID \
  --output-dir ./workflo-artifacts
workflo verify \
  --offline \
  --receipt ./workflo-artifacts/receipt.json \
  --evidence ./workflo-artifacts/evidence/ \
  --trust-key ./trusted-workflo-key.pem
```

Exact command spelling may be adjusted by the CLI contract owner, but the semantics are fixed:
- full commit SHA is visible and immutable;
- the chosen runner is explicit or deterministically resolved from an authorized pool;
- the CLI distinguishes admitted/queued/running/completed;
- verification is local and does not call the control plane or provider;
- exit codes distinguish usage, authentication/authorization, admission, execution, QA, trust verification and infrastructure failures;
- a nonzero exit on failed verification cannot be overridden by a successful test result.

## 5. Independent acceptance tests

| ID | Scenario | Required result |
|---|---|---|
| M1-01 | Valid pinned commit, one passing pytest fixture | Real VM boots, tests execute, clean teardown, valid offline receipt |
| M1-02 | Same commit with deterministic failing test | VM and receipt valid; QA outcome failed; trust may still be verified if evidence/teardown are valid |
| M1-03 | Branch moves after ref resolution | Admitted SHA remains unchanged |
| M1-04 | Invalid/missing commit or repository access denied | Admission rejected; no VM provisioned |
| M1-05 | Guest attempts host filesystem/network access | Access denied; event/evidence captured; no host modification |
| M1-06 | Guest sends unknown/oversized/replayed protocol message | Rejected; run cannot self-authorize host actions |
| M1-07 | Guest or VMM crashes | Infrastructure/trust outcome is explicit; no verified-clean receipt without proof |
| M1-08 | Teardown probe cannot verify cgroup/network/disk cleanup | Trust is not VERIFIED; receipt either absent or explicitly non-verified per canonical format |
| M1-09 | Evidence byte/hash altered after receipt creation | Offline verification fails |
| M1-10 | Wrong trust key or altered receipt | Offline verification fails |
| M1-11 | Duplicate submission with same idempotency key | One run intent/attempt; no duplicate active VM |
| M1-12 | Runner lease expires during run | Previous attempt is fenced; retry, if any, uses new attempt and fresh VM |
| M1-13 | CLI/runner run with network disconnected after artifacts collected | Offline verification still succeeds |
| M1-14 | CLI run on macOS/Windows client | Client works; strict run dispatches only to eligible remote Linux KVM runner |
| M1-15 | Run on machine without KVM | Strict mode is ineligible; no Docker/bwrap/host-execution fallback |

## 6. Evidence packet required for sign-off

Store the following under a versioned milestone evidence directory, with hashes in the release record:
- exact Workflo main/integration commit SHA;
- exact repository fixture URL and full target commit SHA;
- CLI binary SHA-256, build metadata and toolchain version;
- runner binary SHA-256 and host OS/kernel/architecture;
- Firecracker and jailer version + binary digests;
- guest kernel/rootfs digest;
- RunSpec, signed assignment and policy digest;
- source inventory and digest;
- resource-limit configuration and observed enforcement;
- guest/host protocol transcript (metadata only);
- test report and bounded logs;
- lifecycle and teardown probe output;
- receipt plus signer key ID/fingerprint;
- offline verifier output from a separate clean environment;
- negative-test outcomes and all skipped/blocked checks.

Evidence must not contain GitHub tokens, provider keys, private keys, or uncontrolled source-code copies.

## 7. Agent ownership and task boundary

### DeepSeek — implementation owner
- Start with a read-only audit of `apps/workflo-cli/`, `packages/npm-workflo/`, `packages/workflo-schema/`, `worker/`, `apps/worker-engine/`, Firecracker configuration and current receipt verifier.
- Propose the minimal Go package/module boundary before writing broad scaffolding.
- Implement the native CLI skeleton plus one vertical command path and typed runner client.
- Preserve the Python CLI and Python host as reference until parity.
- Implement Go runner host calls behind the existing narrow Firecracker API; do not add a generic shell command.
- Integrate real Firecracker only after assignment/host protocol and test fixture are frozen.
- Deliver small PRs: CLI bootstrap; run contract client; runner lifecycle; receipt/verify handoff.

### GLM — command/connector/package interface
- Freeze command tree, usage, flags, JSON output and exit-code interface with DeepSeek.
- Audit current connector and package wrappers.
- Define interfaces for GitHub/local source acquisition and immutable SHA resolution.
- Implement command handlers/package-manager distribution only after DeepSeek's interfaces are accepted.
- Keep the CLI command contract separate from Firecracker internals.

### MiniMax — policy and adversarial acceptance
- Turn M1-05 through M1-15 into synthetic, repeatable adversarial fixtures.
- Implement the deterministic policy package only after capability/policy contract review.
- Define test oracles for resource limits, guest/host protocol, source integrity, network policy and teardown failure.
- Independently review DeepSeek's runner changes; do not author and approve the same security-sensitive implementation.

### GPT-6 Luna — control plane and protocol contracts
- Audit current FastAPI run/outbox/attempt/lease/runner/artifact/receipt paths.
- Publish an OpenAPI/protocol delta report before implementation.
- Freeze the first-slice RunSpec, runner assignment/claim/heartbeat/completion protocol, error envelope, idempotency and receipt metadata contract.
- Implement only the backend changes required by the vertical slice; preserve current schemas and legacy endpoints.
- Add PostgreSQL-backed and concurrency/tenant tests where the required production behavior is not yet proven.

### Gemini — dashboard design preparation only
- Audit `apps/dashboard/` and map current routes to accepted API fields.
- Create IA, information hierarchy, design tokens, run state taxonomy and representative synthetic design prototypes.
- Do not build real run/runner/evidence screens against guessed APIs.
- Do not start substantial dashboard implementation before the M1 sign-off.

## 8. Go/no-go rule

M1 is **ACCEPTED** only when every M1-01 through M1-15 case is either passed or explicitly waived by the human owner with a documented residual risk, and the core path has been run on real KVM. Mock tests can support development but never close the real KVM, teardown or offline-verification rows.

If real KVM host access, pinned guest artifacts, signing trust anchor or authorized GitHub access is unavailable, the milestone remains **BLOCKED**. A simulated receipt must never be presented as the milestone result.

## 9. Dashboard release gate

Substantial dashboard work can start only after a signed M1 acceptance record identifies:
- CLI commit and runner commit;
- real KVM host and guest artifacts;
- exact source SHA;
- receipt and offline verifier output;
- independent teardown evidence;
- security test report;
- unresolved findings and human disposition.

Gemini may continue design-system work and API mapping before that point. No feature-complete dashboard or mock production analytics before M1.
