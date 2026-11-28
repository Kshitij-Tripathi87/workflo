# M1 Interface Registry — Producers, Consumers and Frozen Semantics

**Status:** semantic freeze proposal for owner approval on D2; wire-level field names are finalized in the generated OpenAPI and protocol schemas, not guessed by consumers.  
**Scope:** the single M1 CLI → FastAPI → customer runner → Firecracker → receipt workflow.

This registry exists to prevent five agents from independently inventing incompatible interfaces. It describes required semantics, authority and ownership. It does not claim that proposed V2 endpoints or fields already exist.

## 1. Contract authority

1. ADR-0022: strict isolation boundary and threat model.
2. ADR-0024: Go CLI, incremental Go runner migration, Python FastAPI, canonical Python schemas, no big-bang rewrite.
3. Existing canonical source/run/attempt/guest/receipt contracts in `packages/workflo-schema/`.
4. Owner-approved additive M1 OpenAPI and runner protocol version.
5. Generated Go client/types and fixture tests.
6. Agent-local wrappers must not override these semantics.

Human owner approves any change to source identity, run lifecycle, attempt state, guest/host protocol, policy, evidence, signature or trust outcome. Luna owns OpenAPI publication, not unilateral semantic authority.

## 2. Principal and credential boundaries

| Principal | Used by | Credential | May do | Must never do |
|---|---|---|---|---|
| Human CLI user | CLI → control plane | Existing device-flow access token, short-lived | Submit/list/status/cancel runs in server-resolved project scope | Claim runner work, access other tenant IDs, read runner secret |
| Customer runner | Runner → control plane | Separately enrolled runner identity; renewable short-lived credential/certificate | Heartbeat, claim eligible assignment, report bounded state/evidence | Act as human user, widen project scope, submit arbitrary source to guest |
| GitHub source broker | Runner host acquisition path | Short-lived repository-scoped installation credential | Read selected repo/commit and materialize immutable snapshot | Enter guest, RunSpec, stdout, receipt or evidence bundle |
| Guest workload | Inside fresh microVM | Attempt-scoped nonce/capability with strict expiry | Execute profile argv and report bounded structured results | Choose host commands, access credentials, self-report teardown as proof, change policy |
| Receipt signer | Trusted host verification path | Host-held signing key, ideally TPM/OS keystore-backed where available | Sign canonical receipt only after required verification | Accept guest-generated claims as teardown evidence |

The control plane derives user project/tenant scope from authenticated identity and persisted relationships. Client-supplied project/org IDs are selectors, not proof of authorization.

## 3. M1 wire surfaces

Luna publishes the exact OpenAPI paths, auth schemes, request/response bodies and error codes after auditing the current source. The following operations are mandatory; endpoint spelling may be finalized only once, then frozen.

| Operation | Producer → consumer | Required semantics | Owner |
|---|---|---|---|
| User authentication | Control plane → CLI | Existing device-flow login/poll/refresh/revoke behavior; no demo auth in production | Luna |
| Run admission | CLI → control plane | Exact GitHub repo identity + full immutable commit ID + pinned profile/policy + idempotency key | Luna API, DeepSeek client, GLM UX |
| Run read/status | Control plane → CLI | Separate execution, QA and trust outcomes; queued/admitted/running/completed/rejected/cancelled semantics | Luna |
| Cancellation request | CLI → control plane | Request only; never equivalent to verified process/VM termination | Luna + DeepSeek |
| Runner enrollment | One-time enrollment → control plane | Unique runner identity, short expiry, replay protection and revocation | Luna |
| Runner heartbeat | Runner → control plane | Runner identity, software/protocol version, host eligibility, bounded capacity and observed health | Luna + DeepSeek |
| Runner claim | Runner ↔ control plane | Server-authorized assignment, lease expiry, attempt fencing, capacity reservation and duplicate-claim protection | Luna |
| Runner state/completion | Runner → control plane | Attempt-bound monotonic lifecycle; no guest authority over host/trust state | Luna + DeepSeek |
| Source acquisition | Runner broker ↔ GitHub | Repository-scoped short-lived read access; exact full commit and immutable source inventory/digest | GLM + DeepSeek; Luna owns app credentials if brokered |
| Guest protocol | Host ↔ guest | Versioned typed messages; run/attempt/sandbox binding; nonce, sequence, size limits and strict schema | DeepSeek; MiniMax adversarial tests |
| Policy evaluation | CLI/host boundary | Deterministic default-deny decision; profile, argv, capabilities, source/network/resources are versioned | MiniMax; DeepSeek integrates |
| Evidence/receipt metadata | Host → control plane → CLI | Bounded immutable manifest, canonical receipt bytes, signer identity/key ID, digest references | DeepSeek + Luna |
| Offline verification | CLI → local files | No network/provider dependency; verify trust anchor, signature, canonical form, evidence digests and run/source/policy binding | DeepSeek; MiniMax tamper tests |

### 3.1 Required additive V2 capabilities

Expected operation families, subject to source audit and generated OpenAPI:

- `/v2/runs`: create an idempotent run from the human principal.
- `/v2/runs/{run_id}`: read authorized status and the three outcomes.
- `/v2/runs/{run_id}/cancel`: request cancellation.
- `/v2/runners/enroll`: exchange a one-time enrollment proof.
- `/v2/runners/heartbeat`: report health and capabilities.
- runner claim/lease operation: claim one eligible attempt using fencing.
- runner attempt state/completion operation: report monotonic, attempt-scoped result.
- evidence/receipt metadata operation: upload or register bounded artifacts and fetch authorized evidence metadata.

Do not force these into legacy `/v1/runs/complete`, `/logs` or `SandboxExecutor` routes. Keep existing V1 behavior compatible. The strict M1 execution path must not accidentally invoke the legacy `workflo_executor.SandboxExecutor`.

## 4. Source identity and snapshot invariants

- GitHub repository identity must be canonical and unambiguous.
- M1 accepts a full object ID: 40 hex characters for SHA-1 repositories; any SHA-256 repository support must be explicit and versioned. Never accept a shortened SHA as an immutable identity.
- A branch/tag may be used only as an input to resolution. The resolved full object ID is displayed and bound before admission; subsequent ref movement cannot change the admitted source.
- The host acquisition broker fetches exactly that object and computes a canonical source inventory/digest.
- The inventory policy covers file count, total bytes, per-file bytes, path normalization, absolute paths, symlinks, submodules and LFS.
- The guest receives an immutable source artifact. It never sees GitHub tokens or installation credentials.
- No host working-tree mount is passed into the guest.

## 5. Assignment and lease invariants

The exact wire schema must include equivalents of:

- protocol version;
- run ID, attempt ID and unique sandbox ID;
- unique lease ID and expiration;
- source repository + full commit + source digest once materialized;
- pinned profile and policy version/digest;
- guest kernel/rootfs and Firecracker/jailer artifact identities;
- resource ceilings and time/output limits;
- egress/network policy;
- explicit capability allowlist;
- nonce and replay/fencing metadata;
- issuer/key identity and an integrity-protected assignment.

A runner may execute only the active, unexpired assignment it claimed. Replayed, stale, cross-attempt or over-capability messages fail closed. Lease expiry fences the attempt; a retry uses a new attempt ID and a new VM.

## 6. Guest/host protocol invariants

- Typed, versioned messages only; no generic `exec`, shell, filesystem or network proxy operation.
- Every message is bound to run, attempt, sandbox and protocol version.
- Nonce/sequence ordering and replay checks are mandatory.
- Enforce maximum frame, field, nesting, log and artifact sizes before allocation/processing.
- Repository-controlled command text is never interpolated into a host shell.
- Guest-reported shutdown is a request/result, not host teardown evidence.
- Unknown operation, schema mismatch, expired capability or wrong attempt is rejected and audited without echoing secrets.

## 7. Outcomes, evidence and receipt

Keep these axes independent:

| Axis | Example values | Authority |
|---|---|---|
| Execution | queued, claimed, provisioning, running, completed, infrastructure_failed, cancellation_pending/cancelled | Control plane + host lifecycle |
| QA | not_run, passed, failed, partial | Structured profile report, validated by host |
| Trust | pending, verified_clean, verification_failed, cleanup_incomplete, unknown | Independent host verifier + offline receipt verifier |

A QA failure can still produce a valid signed receipt if execution, evidence and teardown integrity pass. A trust failure must never be represented as a clean pass.

Reuse existing canonical Receipt V5/DSSE and MicroVM teardown contract. The eight existing MicroVM teardown checks must remain present and host-observed: VMM exited, VM stopped, cgroups removed, netns removed, disk destroyed, sockets closed, capabilities expired, and process scope empty. Do not map the three-check namespace/dev teardown schema to a MicroVM run. Missing/unknown teardown evidence blocks VERIFIED_CLEAN.

## 8. M1 contract tests

| Test ID | Contract assertion | Owner |
|---|---|---|
| IF-01 | V1 API and existing receipt fixtures remain compatible | Luna + DeepSeek |
| IF-02 | CLI cannot submit a shortened/mutable source identity | DeepSeek + GLM |
| IF-03 | Same idempotency key creates one run intent/active attempt | Luna |
| IF-04 | User principal cannot claim runner assignment | Luna + MiniMax |
| IF-05 | Runner principal cannot read another project's run | Luna + MiniMax |
| IF-06 | Expired/replayed runner enrollment or lease is rejected | Luna + MiniMax |
| IF-07 | Two runners cannot hold active authority for same attempt | Luna |
| IF-08 | Guest cannot request arbitrary host command or widen capability | DeepSeek + MiniMax |
| IF-09 | Wrong-attempt/replayed/oversized guest messages are denied | DeepSeek + MiniMax |
| IF-10 | GitHub credential is absent from guest, RunSpec, logs, receipt and evidence | GLM + MiniMax |
| IF-11 | Missing teardown field prevents verified-clean trust outcome | DeepSeek + MiniMax |
| IF-12 | Altered evidence/receipt or untrusted key fails offline verification | DeepSeek + MiniMax |
| IF-13 | CLI verification performs no network access | DeepSeek |
| IF-14 | No-KVM host rejects strict run without dev fallback | DeepSeek + MiniMax |
| IF-15 | Control-plane restart/retry does not duplicate active attempt | Luna |

## 9. M1 non-goals

No org membership/roles, invitations, provider credential management, inference routes, dashboard aggregation, GitHub webhook/check publishing, billing, hosted fleets, broad quota/fairness system or 15-user/45-submission load claim. These are post-M1 contracts and require their own scope and acceptance.

## 10. Change process

A change request must state: contract ID, reason, current producer/consumer, exact compatibility impact, data/security impact, migration strategy, tests and rollback. The owner approves before any shared contract is edited. Luna publishes the generated OpenAPI and fixtures; DeepSeek/GLM consume generated artifacts. Reviewers reject hand-maintained divergent mirrors.
