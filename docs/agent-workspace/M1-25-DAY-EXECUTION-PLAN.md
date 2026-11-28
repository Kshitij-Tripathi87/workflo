# M1 Delivery Plan — 25-Day Critical Path

**Programme start:** 29 November 2026  
**Target M1 acceptance:** 23 December 2026 (Day 25)  
**Planning baseline:** current `main` when this plan is merged  
**Milestone:** native Go CLI → authenticated control plane → customer Linux/KVM runner → fresh Firecracker microVM → signed receipt → offline verification  
**Status:** execution plan; not evidence of implementation or acceptance

> **Delivery rule:** Day 25 is a target for the narrow M1 vertical slice, not a promise that unproven security gates will be waived. If real KVM, teardown, signing, source integrity or offline verification is not proven, M1 remains BLOCKED and no beta claim is made.

## 1. The one result that matters

A user runs the native Go `workflo` CLI against an exact GitHub commit. The user authenticates through the existing device authorization flow. The FastAPI control plane admits the request using a required idempotency key and its durable outbox. An enrolled customer-controlled Linux x86_64 KVM runner claims a fenced attempt. The runner uses the existing Firecracker host implementation under `worker/` as the M1 execution reference, boots a **fresh** Firecracker microVM, acquires only the pinned source revision, executes one pinned Python/pytest profile, collects bounded evidence, independently verifies host teardown, signs the canonical receipt, and the CLI verifies the receipt offline with a configured trust anchor.

The three result axes stay separate:

- **Execution:** infrastructure lifecycle outcome.
- **QA:** whether the selected test profile passed or failed.
- **Trust:** whether source, evidence, signature and teardown were independently verified.

A valid test failure can have a valid receipt. A passing test cannot turn an incomplete teardown into a trusted run.

## 2. Architecture decisions that remove the sequencing conflict

These decisions are binding for M1 and supersede conflicting work-package wording in older runbooks. They do not silently change ADR-0024 or canonical receipt semantics.

| Area | M1 decision | Explicitly not an M1 dependency |
|---|---|---|
| CLI | New native Go executable in `apps/workflo-cli-go/`; no Python/Node/model runtime required by the CLI | Full parity with every legacy Python CLI command |
| Control plane | Existing FastAPI/Python app; additive, separately versioned M1 API; preserve V1 | Go rewrite, broad API redesign |
| Customer runner | Integrate current Python Firecracker host under `worker/` through a narrow, versioned adapter; preserve it as the reference implementation | Big-bang Go host rewrite or a second Firecracker implementation |
| Runner migration | DeepSeek records the Go runner boundary and may prototype isolated protocol bindings only if it does not delay M1; Go runner parity is a post-M1 workstream | Requiring a new Go runner to pass M1 while the existing Python KVM host is not yet wired end-to-end |
| Identity | Existing OAuth device flow for the human CLI principal; existing server-resolved personal project context | Organization membership, invitations, Owner/Admin/Developer/Viewer RBAC |
| Runner identity | Distinct, one-time enrollment and renewable short-lived runner credential; attempt/lease fencing | Reusing human access tokens or GitHub tokens as runner identity |
| Source | GitHub repository + immutable full commit SHA; runner-side source broker; no credentials in guest | Local-folder connector, multi-VCS, source upload to hosted models |
| Execution | One Linux x86_64 KVM runner; one pinned Firecracker/jailer + guest kernel/rootfs; one fresh VM per attempt | macOS/Windows strict local execution, ARM64, Docker/bwrap fallback |
| Test profile | One pinned Python + pytest profile, bounded command argv and outputs | Node/Go/Java profiles, app/browser exploration |
| Receipt | Reuse canonical existing receipt/signing/verifier contracts; additive fields only through approved version | Inventing a new receipt format or weakening verification |
| AI | No model or provider required for the M1 core path | Deep AI mode, hosted inference, BYOK integration |
| Web | Gemini produces IA, tokens, components and synthetic prototype only until signed M1 acceptance | Production dashboard screens, fake analytics, second backend |
| Scale | Admission/idempotency/lease correctness and bounded queue behavior for the single-run vertical slice | 15-user/45-submission beta capacity claim |

### 2.1 Why the Python host remains for M1

ADR-0024 explicitly makes Go the target language for the customer-runner host **incrementally** and retains the existing Python host as the behavioral and integration reference until Go passes contract parity, real KVM Gate B and end-to-end receipt verification. The repository already has a Python Firecracker/jailer lifecycle foundation; it is not yet connected to the API dispatch path.

For a 25-day M1, DeepSeek must connect and prove that existing host path rather than build a second host implementation in parallel. The CLI must be native Go and must not require Python. The customer runner may use the current Python host package/runtime in this milestone; its installation and runtime requirements must be stated honestly. A later Go runner migration must pass the same real-KVM fixtures before replacing the reference.

### 2.2 Luna's corrected M1 scope

GPT-6 Luna is the **M1 control-plane integrator**, not the owner of every future platform feature. Luna must implement only what the critical path requires:

1. compatible human CLI authentication using the existing device-flow identity;
2. server-side resolution of the user's existing project/tenant scope;
3. additive versioned run admission and run status;
4. runner enrollment, heartbeat, claim/lease, completion and revocation primitives;
5. idempotent run + attempt + outbox admission;
6. a dispatch bridge to the existing Firecracker host adapter;
7. bounded artifact/receipt metadata storage and retrieval;
8. PostgreSQL integration/RLS tests for the actual M1 project-scoped access path;
9. generated OpenAPI/client contract and operator handoff.

Luna must **not** block M1 on organizations/memberships, team roles, invitations, GitHub check publishing, hosted inference/BYOK, dashboard aggregation APIs, broad audit/usage analytics, or the 15-user/45-submission target. Keep those in the post-M1 backlog with explicit dependencies. Do not create a fake personal-workspace or membership API if the current OAuth/user/project model can supply the authorized project context.

## 3. Critical-path dependency graph

```text
BASELINE AUDIT + CALIBRATION + REAL KVM HOST ACCESS
                         |
             M1 INTERFACES FREEZE (owner approved)
                         |
           +-------------+-----------------+
           |                               |
     Go CLI core                    FastAPI V2 contracts
   DeepSeek + GLM                    GPT-6 Luna
           |                               |
     CLI consumer + auth/run submission ---+
                         |
              runner enrollment/claim
                         |
           existing Python Firecracker host
             behind narrow runner adapter
                         |
       exact GitHub source + pinned pytest profile
                         |
       guest protocol + limits + evidence collection
                         |
         independent host teardown verification
                         |
             canonical signed receipt
                         |
              offline CLI verifier
                         |
       MiniMax negative/adversarial acceptance
                         |
      clean-machine end-to-end + signed M1 decision
                         |
             Gemini production UI may start
```

**Parallel tracks:** MiniMax builds synthetic threat fixtures and reviews the boundary while DeepSeek/Luna implement; GLM freezes command UX and develops connector tests against the agreed interface; Gemini does design preparation with synthetic data only. Parallelism must not create duplicate producers for shared contracts.

## 4. Work ownership and file boundaries

| Agent | Sole primary ownership | Must coordinate with | Prohibited ownership |
|---|---|---|---|
| DeepSeek | Go CLI core; M1 client/runner protocol consumer; minimal adapter integration into existing host as agreed | Luna on API; GLM on command handlers; MiniMax on host boundary | FastAPI business logic, canonical schema/receipt semantics, policy default changes, dashboard |
| GLM | CLI command tree/handlers outside reserved core; GitHub source connector and SHA resolution; output/error UX; packaging design/tests | DeepSeek on CLI interfaces; Luna on GitHub auth/source API | CLI entrypoint/core transport duplication, Firecracker host, policy, backend auth |
| MiniMax | Threat model, policy test suite, synthetic adversarial fixtures, independent security review/report | DeepSeek on host/protocol; Luna on auth/tenant/receipt storage | Sole approval of own fixes, production target testing, unrestricted exploit tooling, changing defaults to green CI |
| GPT-6 Luna | FastAPI V2 API, DB migration/service/router, durable dispatch/runner identity, OpenAPI and backend tests | DeepSeek runner contract; GLM source auth; MiniMax privacy/security; Gemini types | Go CLI/runner internals, canonical receipt semantics, dashboard UI, production deployment |
| Gemini | IA/design tokens/components/static prototype/browser test plan | Luna for actual schemas; owner for product semantics | Production dashboard/API integration before M1; guessed endpoints; fake live data; runner/guest direct calls |

Every file outside an agent's primary ownership requires the owning agent's review or an explicit one-task ownership transfer. Shared contracts are reserved, versioned and owner-approved before code consumers merge.

## 5. Twenty-five-day execution calendar

Daily work is demo-driven. Each day ends with a commit/PR, exact test evidence, blockers and next-day objective. The integrator reviews and merges small compatible slices daily; agents do not hold completed work until the end.

| Day / date | Critical deliverable | Primary owners | Exit evidence |
|---|---|---|---|
| **D1 · Nov 29** | Baseline audit; exact repo SHA; model IDs/harness captured; KVM machine, Firecracker artifacts, signer/trust-anchor and GitHub test repo access confirmed | All; Luna consolidates | Audit reports; environment inventory; blockers logged; calibration ledger updated only with actual runs |
| **D2 · Nov 30** | Freeze CLI command semantics, M1 API endpoints, assignment/lease fields, source digest rules, guest message invariants and receipt reuse path | Luna + DeepSeek + GLM + MiniMax; owner approves | Contract review record; OpenAPI draft; protocol compatibility matrix; no unapproved canonical schema mutation |
| **D3 · Dec 1** | Native Go CLI skeleton: build, version, help, config layout, stable error codes, JSON mode; command tree tests | DeepSeek; GLM | Linux build and `--help/--version`; cross-platform build pipeline draft |
| **D4 · Dec 2** | CLI authentication/device-flow client and project selection; doctor reports client vs remote strict-runner eligibility | DeepSeek + GLM + Luna | Auth lifecycle tests; no token in logs; no Python/Node dependency in Go CLI |
| **D5 · Dec 3** | Run request client, idempotency key, immutable SHA validation, dry-run, status polling and cancellation semantics | DeepSeek + GLM + Luna | Golden request/response fixtures; invalid/abbreviated SHA rejected before admission |
| **D6 · Dec 4** | Luna lands additive V2 human API and database-backed idempotent admission using existing run/attempt/outbox primitives | Luna | PostgreSQL integration tests; duplicate request creates one intent; V1 compatibility suite green |
| **D7 · Dec 5** | Runner identity enrollment, heartbeat, capabilities and revoke; first customer runner can register | Luna + DeepSeek | Enrollment/revocation tests; runner principal distinct from user/API key |
| **D8 · Dec 6** | Claim/lease protocol with attempt fencing; runner health/capacity eligibility; claim cannot produce overlapping active attempts | Luna + DeepSeek + MiniMax | Race/expiry/replay tests; signed/expiring assignment or approved authenticated equivalent |
| **D9 · Dec 7** | Connect V2 dispatch to existing worker host adapter; eliminate M1 path through legacy `SandboxExecutor` for strict runs | Luna + DeepSeek | Integration test proves V2 strict run dispatches to Firecracker host adapter, not legacy executor |
| **D10 · Dec 8** | Host adapter provisions pinned Firecracker/jailer and fresh VM on actual KVM; first guest handshake | DeepSeek; MiniMax reviews | Real KVM boot transcript + artifact digests; mock labelled separately |
| **D11 · Dec 9** | Exact GitHub commit source acquisition and immutable snapshot digest; host-held token lifecycle | GLM + DeepSeek + Luna | Source manifest; branch-movement and digest tests; no credential in guest/logs/receipt |
| **D12 · Dec 10** | Guest handshake, attempt binding, typed protocol, replay/oversize rejection and pinned pytest argv | DeepSeek + MiniMax | Positive guest test + negative protocol suite on actual KVM where required |
| **D13 · Dec 11** | CPU/RAM/disk/PID/time/output bounds and default-deny network; dependency preparation separated from sealed test phase | DeepSeek + MiniMax | Enforcement evidence, hostile fixture outcomes and teardown fault injections |
| **D14 · Dec 12** | Bounded logs/test report/evidence manifest; source/policy/runtime/evidence digests | DeepSeek + Luna | Evidence manifest contract tests; size caps and secret-redaction checks |
| **D15 · Dec 13** | Independent host teardown probes for all required MicroVM checks; fail-closed trust classification | DeepSeek + MiniMax | VMM/VM/cgroup/netns/disk/socket/capability/process-scope results; deliberate teardown failure blocks VERIFIED_CLEAN |
| **D16 · Dec 14** | Receipt signing/verification integration using canonical receipt contract; signer identity and trust anchor handling | DeepSeek + Luna; MiniMax review | Valid receipt fixture; no guest self-signing; canonical verifier tests |
| **D17 · Dec 15** | Offline CLI `verify`; verify signature, trust anchor, canonical encoding, evidence hashes and source/run/policy/runtime binding | DeepSeek + GLM | Verification succeeds on network-disabled clean machine; tamper/wrong-key tests fail |
| **D18 · Dec 16** | First full vertical slice from native CLI through real Firecracker to offline verification | All critical owners | One reproducible run on a named KVM host; evidence packet skeleton complete |
| **D19 · Dec 17** | Negative acceptance M1-01..M1-08; test failure vs infrastructure vs trust outcome separation | MiniMax + DeepSeek + Luna | Pass/fail evidence matrix, issue owners and regression tests |
| **D20 · Dec 18** | Negative acceptance M1-09..M1-15; idempotency, lease expiry, no-KVM fail-closed, remote runner from macOS/Windows client builds | MiniMax + all | No fallback; tamper/wrong-key/duplicate/expired-lease cases evidenced |
| **D21 · Dec 19** | Clean-checkout reproducibility; installer/build artifacts for CLI targets; Python legacy behavior comparison | DeepSeek + GLM | Linux/macOS/Windows CLI smoke; no claim of strict local execution outside Linux/KVM |
| **D22 · Dec 20** | Backend recovery, API auth/RLS, restart, duplicate dispatch and runner restart verification | Luna + MiniMax | PostgreSQL-backed tests; non-owner role where production RLS is required; no duplicate active VM |
| **D23 · Dec 21** | Independent review, threat-model closure, artifact provenance, SBOM/checksums and known-limitations register | MiniMax + owner + all | Independent review report; all open findings severity/owner/disposition recorded |
| **D24 · Dec 22** | Release-candidate freeze; repeat all M1 tests against one immutable integration SHA; assemble evidence packet | Integrator + all | M1-01..M1-15 matrix, exact artifact digests, real/mock labels, clean-machine verifier result |
| **D25 · Dec 23** | Formal owner go/no-go and M1 acceptance decision; tag candidate only if all hard gates pass | Human owner; all submit evidence | Signed acceptance record or explicit BLOCKED decision with named blockers and recovery dates |

### Daily operating rhythm

- **09:30 IST:** each agent posts yesterday's evidence, today's one primary outcome, blockers and file reservation needs.
- **13:00 IST:** 15-minute integration checkpoint; unblock cross-agent interfaces; no status-only meetings.
- **18:30 IST:** PR-ready checkpoint; run exact targeted tests and attach logs/results.
- **20:00 IST:** integrator updates the milestone board, merges only reviewable green slices, rebases dependent branches and posts tomorrow's dependencies.
- Do not allow a blocker to sit for a full day: escalate a missing contract/environment/permission immediately to the owner.

## 6. Agent work package sequencing

### DeepSeek — implementation critical path

1. Audit current CLI, schema, host and guest; map exact reuse boundary.
2. Implement the Go CLI core and API client first.
3. Wire only the M1 command set: `--version`, `--help`, `auth login/status/logout` as supported by existing auth, `doctor`, `run`, `status`, `cancel`, `verify`.
4. Connect V2 runner messages to the existing Firecracker host implementation; no second VM manager.
5. Ensure every attempt creates a fresh VM and every host teardown check is collected by the host.
6. Implement receipt handoff and offline verification.
7. Maintain a separate post-M1 design for Go runner parity; do not make it a D1–D25 dependency.

### GLM — client interface and source acquisition

1. Freeze command UX/flags/output/exit-code golden fixtures with DeepSeek.
2. Implement handlers through DeepSeek's approved interfaces, not a parallel entrypoint.
3. Resolve GitHub refs to full immutable object IDs; reject abbreviated/moving references at admission.
4. Define repository size/path/symlink/submodule/LFS policy with MiniMax and DeepSeek.
5. Ensure installation/package behavior does not install Python into the CLI runtime.
6. For M1, provide build/test artifacts and clean-install smoke tests; public npm release and all package managers are post-M1.

### MiniMax — independent security and adversarial acceptance

1. Map each trust boundary and create named test IDs before implementation.
2. Test allow/deny branches, source limits, network isolation, resource bounds and protocol parsing.
3. Review host launch arguments and teardown proof with a human security reviewer.
4. Ensure a guest/model cannot authorize a host operation or broaden its own capabilities.
5. Inspect actual outbound/serialized data paths; M1 core must not call a model provider.
6. Reproduce each finding; assign severity, fix owner and regression test; no self-approval.

### GPT-6 Luna — M1 backend integrator

1. Audit current auth, project model, runs API, outbox, attempts, dispatcher and Firecracker host library.
2. Freeze the smallest additive V2 contract with DeepSeek/GLM/MiniMax before route implementation.
3. Keep the V1 API unchanged and route M1 strict runs through runner claim/lease, not `SandboxExecutor`.
4. Enforce server-side project scope, idempotency and lease fencing.
5. Integrate runner adapter to existing host without claiming Go host migration is complete.
6. Expose only run status and receipt/evidence metadata needed by CLI.
7. Produce real PostgreSQL/auth/RLS/race tests and operator handoff.
8. Move org membership, inference, GitHub webhook publishing, analytics and 45-submission load target to post-M1.

### Gemini — bounded parallel design work

1. Audit current dashboard and map it to real API fields.
2. Define run-state language, three result axes, design tokens and component contracts.
3. Build only a static, visibly synthetic prototype and accessibility plan before M1 acceptance.
4. Do not commit production API-dependent views or mock analytics as working features.
5. After M1 acceptance, take a new bounded task for read-only Runs list/detail/evidence views against generated types.

## 7. M1 interface freeze and change control

The authoritative contract stack is:

1. Accepted ADRs, especially ADR-0022 and ADR-0024.
2. `M1-INTERFACE-REGISTRY.md` for cross-agent ownership and semantic invariants.
3. The owner-approved OpenAPI and generated Go/TypeScript client fixtures.
4. Existing canonical Python schema and receipt contracts.
5. Agent runbooks for implementation details.

A missing field is not a reason to guess. Open a contract change with: reason, exact producer/consumer impact, migration/compatibility plan, tests and owner decision. No agent edits the shared canonical schema, lifecycle enums, receipt semantics, assignment protocol or policy defaults without reservation and approval.

## 8. Test and evidence classifications

Every reported result must be labelled exactly one of:

- **UNIT:** isolated pure code or component tests.
- **MOCKED-INTEGRATION:** API/runner/provider mocked; useful but not proof of real execution.
- **LOCAL-INTEGRATION:** multiple real services on developer infrastructure, but not real Firecracker/KVM.
- **REAL-KVM:** Firecracker boots on the named Linux x86_64 KVM host with exact pinned artifacts.
- **OFFLINE-VERIFICATION:** verifier executes on a separate clean environment with network unavailable.

Only REAL-KVM can satisfy VM/host isolation and teardown rows. Only OFFLINE-VERIFICATION can satisfy offline receipt rows. No skipped, unsupported or mocked test can be converted to PASS.

## 9. Hard gates and rollback rules

- No-KVM host: strict run rejected; no Docker, bwrap, namespace-only or host-process fallback.
- Missing/expired runner identity or lease: reject/stop and fence attempt.
- Missing source digest or abbreviated commit: reject before provisioning.
- Unknown/oversized/replayed guest message: deny and audit.
- Teardown check unknown/failed: trust is not VERIFIED_CLEAN.
- Receipt/evidence signature or digest mismatch: offline verifier exits nonzero.
- V1 compatibility regression: revert the V2 integration slice; do not patch V1 semantics as a shortcut.
- Critical/high security issue: block acceptance until fixed and independently retested, or record explicit owner-approved residual-risk exception only where legally/technically permissible. No exception can turn missing teardown proof into verified trust.

## 10. Out of scope and post-M1 queue

- Go customer-runner full parity and migration away from Python host.
- Local-folder and multi-VCS connector, unless already supported by an existing stable API and it does not extend M1 critical path.
- Node, Go and Java guest profiles.
- Deep AI testing, BYOK/provider gateway, consent and model-tool authorization.
- Organization memberships/invitations/RBAC and team workspace UX.
- GitHub PR/check webhook automation.
- Public npm/pnpm/Bun package publishing and signed native installer releases.
- Feature-complete dashboard and usage/analytics.
- 15-user/45-submission load target and hosted runner fleet.
- Automatic patches, merge, deploy, billing and marketplace.

Each item receives a post-M1 owner, estimate and dependency; none may be smuggled into M1 acceptance.

## 11. Acceptance record template

```yaml
milestone: M1
decision: ACCEPTED_OR_BLOCKED
decision_date: YYYY-MM-DD
integration_commit: FULL_SHA
cli_artifact_sha256: SHA256
runner_host_artifact_sha256: SHA256
host_os_kernel_arch: EXACT_VALUE
firecracker_version_sha256: EXACT_VALUE
jailer_version_sha256: EXACT_VALUE
guest_kernel_sha256: SHA256
guest_rootfs_sha256: SHA256
source_repository: URL
source_commit_sha: FULL_SHA
source_snapshot_digest: DIGEST
profile_id_version: EXACT_VALUE
policy_digest: DIGEST
receipt_digest: DIGEST
signer_key_id: KEY_ID
offline_verification: PASS_OR_FAIL
real_kvm_cases: PASS_FAIL_SKIP_COUNTS
security_findings: []
waivers: []
blockers: []
owner_approval: HUMAN_RECORDED
```

## 12. Definition of done

M1 is accepted only when M1-01 through M1-15 have recorded evidence, all mandatory real-KVM and offline-verification cases pass, no critical/high unresolved security/privacy defect remains, V1 compatibility is preserved, the evidence packet is reproducible and the human owner signs the acceptance record.
