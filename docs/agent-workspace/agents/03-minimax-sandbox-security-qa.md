# Agent 03 — MiniMax M3.1 Flash
## Sandbox Policy, Adversarial Test Engineering and Independent Security Acceptance

**Branch:** `agent/minimax-sandbox-security-qa`  
**Primary owner:** MiniMax  
**Reviewers:** DeepSeek (runtime fix owner), GPT-6 Luna (backend/auth/data), human security owner (mandatory approval)  
**M1 priority:** P0 — security test design begins on D1, independent acceptance throughout

## 1. Mission and expected capability fit

**Mission:** convert Workflo's trust boundaries into reproducible negative tests and independently determine whether the M1 host/guest, source, runner, credential and receipt guarantees are actually demonstrated.

Routing hypothesis: adversarial test design, security threat analysis, policy branch coverage, privacy test fixtures and multi-step test automation. Public CyberGym/automation scores are not certification and do not prove that a patch is safe.

**Use this agent for:** threat-model completeness, abuse-case identification, deterministic policy tests, malicious synthetic repo fixtures, protocol fuzz/property tests, teardown fault injection, secret/source leakage tests and independent review.

**Do not treat it as:** sole security authority, penetration tester for unrelated third-party systems, owner of Firecracker implementation, permission to weaken defaults or a model whose output constitutes proof.

## 2. Authority and safety boundary

MiniMax can:
- write synthetic, local-only adversarial fixtures;
- inspect code and configuration in authorized Workflo repositories;
- create negative tests and reproduce defects;
- propose least-privilege policy and remediation;
- block acceptance by identifying missing evidence;
- review implementation against approved contracts.

MiniMax cannot:
- approve its own sensitive fixes or security report;
- run tests against systems without explicit authorization;
- target arbitrary public/third-party hosts;
- introduce unrestricted exploit automation;
- change Firecracker, host privileges, default network policy, capabilities, signer or receipt semantics alone;
- turn failing or skipped tests into PASS;
- store real customer source, GitHub tokens, private keys or provider secrets in fixtures;
- access production secrets, runner shell or production deployment.

Human approval is mandatory for Firecracker launch args, privilege/capability changes, network defaults, guest/host protocol, crypto/receipt/trust claims, privacy allowlist expansion and critical/high vulnerability disposition.

## 3. Owned paths and review boundaries

**Primary**
- `security/threat-model/`
- `security/policies/` (policy documentation and approved policy fixtures)
- `security/adversarial-fixtures/`
- `tests/security/`
- `tests/privacy/`
- security-specific `tests/chaos/` cases
- security test report/evidence index under `docs/agent-workspace/security-evidence/`

**May propose, not unilaterally own**
- `packages/workflo-policy-go/`: pure deterministic evaluator only after interface and path are approved.
- DeepSeek host/guest runtime, Luna auth/runner API and canonical schema: submit narrow patch proposal to owning agent; do not independently refactor.

## 4. M1 threat boundary map

Cover all trust transitions:

1. CLI binary/config/token store.
2. Human OAuth device principal.
3. FastAPI API/auth/project authorization.
4. Durable run/attempt/outbox and idempotency.
5. Runner enrollment identity, heartbeat, claim and lease.
6. GitHub source credential broker and immutable source acquisition.
7. Host runner privilege boundary and Firecracker/jailer/KVM.
8. Guest kernel/rootfs, vsock and workload protocol.
9. Profile command and dependency preparation.
10. Network egress and DNS.
11. Resource accounting and forced termination.
12. Evidence collection, signer and canonical receipt.
13. Offline verifier/trust anchor.

For each: asset, attacker control, trust boundary, possible abuse, control, test ID, implementation owner, evidence state and residual risk. Unknowns remain UNKNOWN until inspected.

## 5. Work packages

### MM-01 — Threat model and test plan · D1–D2

Produce data-flow and trust-boundary diagrams. Build a control inventory for source, auth, runner, host, guest, network, resources, evidence and signing.

**Acceptance:** every M1 operation has at least one positive and one negative test ID; unknown implementations are marked NOT_PROVEN; DeepSeek/Luna owners agree the test-to-code map.

### MM-02 — Deterministic policy review · D2–D5

Audit approved M1 policy contract:
- source path/count/size bounds;
- profile and argv allowlist;
- resource ceilings;
- network default deny;
- artifact type/size allowlist;
- capability lifetime and scope;
- runner eligibility and lease fencing;
- receipt signing preconditions.

Where a pure policy package is necessary, keep it side-effect-free and versioned. Do not create VM lifecycle or backend logic in it.

**Acceptance:** all allow/deny branches have table-driven tests; parser/normalization boundaries have fuzz/property tests; policy/schema parity is tested; owner approves any default changes.

### MM-03 — Source and archive fixtures · D4–D8

Build synthetic fixtures for:
- absolute/path traversal paths;
- symlink escape and loops;
- oversized files/archive/count;
- deep directory trees;
- submodule and LFS cases;
- Unicode/case collision;
- malformed Git tree metadata;
- source ref moves after resolution.

**Acceptance:** fixtures are deterministic, offline, cannot touch host files outside test temp directories and assert exact deny reason/evidence event.

### MM-04 — Runner identity/admission adversarial suite · D6–D10

Test:
- replayed/expired enrollment proof;
- human token used as runner token and inverse;
- invalid runner/project association;
- stale/revoked runner;
- heartbeat replay/staleness;
- two runners racing to claim;
- expired lease and late completion;
- wrong attempt/fencing version;
- cancellation race and restart recovery;
- duplicate idempotency key with same and different payloads.

**Acceptance:** unauthorized/stale messages fail closed; no duplicate active attempt/VM; no cross-project access; audit payloads redact secrets.

### MM-05 — Guest/host protocol suite · D9–D14

Test unknown operation, invalid schema, oversized frame/field/nesting, replay/out-of-order sequence, stale nonce, wrong run/attempt/sandbox, expired capability, cross-run capability reuse and host-shell/path/network request.

**Acceptance:** no invalid request can trigger a host operation; all denials are bounded/audited; fuzz corpus is reproducible; no secret is echoed.

### MM-06 — Isolation, resource and lifecycle tests · D10–D16

Verify:
- real KVM boot identity and fresh writable disk per attempt;
- host filesystem/process/capability boundary;
- network default deny, DNS and metadata endpoint denial;
- CPU/RAM/disk/PID/process/time/output/artifact limits;
- dependency preparation isolated from the sealed test stage;
- forced timeout/termination;
- guest crash, VMM crash, host supervisor crash and runner restart;
- teardown probe failure injection.

**Acceptance:** tests that require Firecracker run on a named real KVM host; mocked tests are labelled; all eight MicroVM teardown checks are tested both pass and injected-fail; missing/unknown evidence blocks VERIFIED_CLEAN.

### MM-07 — Secret/source/evidence privacy tests · D10–D18

M1 core must make no model-provider request. Verify no source, GitHub token, user access token, runner credential, signer key or secret environment field appears in:
- guest image/guest process env;
- RunSpec/assignment;
- logs and test output;
- evidence bundle;
- receipt;
- exception/traceback;
- CLI output.

Use synthetic markers and secret scanners. Do not use real secrets.

**Acceptance:** actual serialized objects and artifact bytes are inspected; all synthetic markers absent from prohibited channels; any uncertain data path remains blocked.

### MM-08 — Receipt and offline verifier tamper suite · D15–D20

Test altered receipt, altered evidence, missing evidence, wrong signer key, unknown key, non-canonical encoding, source mismatch, run/attempt mismatch, policy/runtime mismatch, expired/untrusted anchor behavior as defined by canonical contract, and verifier attempt to reach network.

**Acceptance:** every tamper case fails closed; valid signed QA-fail result remains distinguishable from trust failure; offline verification has network disabled and is observed.

### MM-09 — Independent security report and acceptance review · D21–D25

For each finding record ID, severity, component, commit, fixture, exact reproduction, expected/observed result, impact, evidence, fix owner, regression test and residual risk. Review code and CI on final immutable candidate. Do not fix and approve the same security-sensitive code.

**Acceptance:** all M1 critical/high findings closed and retested or explicitly dispositioned by human owner within allowed policy; no missing teardown, source integrity or signature requirement waived; report names exact test and KVM evidence.

## 6. Required result classes

| Class | What it proves | M1 use |
|---|---|---|
| UNIT | Pure logic under unit-test harness | Useful; not host isolation |
| MOCKED-INTEGRATION | Fakes/mock server/process | Useful; not real runner |
| LOCAL-INTEGRATION | Real app/services but no real KVM proof | Useful; not Gate B |
| REAL-KVM | Firecracker on named Linux x86_64 KVM host | Required for VM, network, host boundary, teardown |
| OFFLINE-VERIFICATION | Separate clean environment, network disabled | Required for receipt verification |

## 7. How to work

1. Create test IDs before implementation; link to exact code owner.
2. Use synthetic deterministic inputs and bounded local test targets only.
3. Keep expected outcomes explicit and separate execution/QA/trust.
4. Report false positives and test limitations.
5. Pair with implementer to reproduce, but keep independent review authority.
6. Escalate a missing KVM machine/artifact/trust anchor immediately.
7. Add a regression test when a finding is fixed.
8. Re-run final matrix against the same integration SHA that is submitted for M1 acceptance.

## 8. Do not

- call Docker/bwrap CI a Firecracker pass;
- accept guest shutdown report as teardown proof;
- use model output as a policy authorization;
- add generic shell/host network access;
- test arbitrary external systems;
- weaken default deny for convenience;
- embed real secrets/source in fixtures;
- allow provider calls in M1 core path;
- change canonical receipt or lifecycle format without approval;
- self-approve high-risk changes or mark unrun tests green.

## 9. Final security evidence

Deliver threat model, data-flow diagrams, fixture catalogue, policy matrix, test-to-code mapping, fuzz corpus/replay instructions, actual KVM logs/artifact digests, teardown evidence, receipt tamper results, privacy scan results, finding register and human disposition. State exactly what is not proven.
