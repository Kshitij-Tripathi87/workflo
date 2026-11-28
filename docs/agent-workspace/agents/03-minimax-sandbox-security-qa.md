# Agent 03 — MiniMax M3.1 Flash
## Deterministic Policy Engine, Sandbox Security, Privacy QA and Adversarial Acceptance

**Workstream:** Trust, security and policy — independent assurance  
**Branch:** `agent/minimax-sandbox-security-qa`  
**Implementation owner:** MiniMax M3.1 Flash  
**Implementation partners:** DeepSeek (Go host/runtime), GPT-6 Luna (API/privacy persistence), GLM (connector/CLI integration)  
**Required reviewers:** DeepSeek for host behavior, GPT-6 for control-plane/privacy contract, human security owner for every high-impact boundary and release acceptance.

---

## 1. Mission and expected result

Own Workflo's deterministic security policy package, threat model and adversarial acceptance suite. Your job is to prove that the CLI, connector, runner, Firecracker host, guest, AI planner, provider gateway and evidence pipeline cannot exceed their approved capabilities.

You are not the sole security authority and must not approve your own implementation. DeepSeek implements host/runner lifecycle; GPT-6 implements backend authentication, tenancy and BYOK APIs; GLM implements the user-facing connector and CLI; MiniMax defines policy, threat cases, deterministic tests and independent security review.

**Expected result:** every important trust boundary has a named owner, explicit allowed/denied behavior, negative tests, evidence and a failure status. The system fails closed when required evidence is missing. No model output alone can authorize a tool or certify a sandbox.

M1 requires real sandbox boundary tests as part of the first verified execution path. The broader customer-facing Security testing gate is a later beta capability and remains separate from Core and Deep AI gate statuses.

## 2. Why this model owns this work

MiniMax M3.1 Flash's official model card reports:
- Automation-Bench v1.0.6: **62.8** (vendor-reported primary value);
- CyberGym: **82.2**;
- DeepSWE v1.1: **73.7**;
- Terminal-Bench 4.0: **38.1**;
- NL2Repo-Bench: **61.2**;
- OSWorld 2.0: **61.7**.

The primary source's evaluation notes identify the benchmark harnesses; a secondary tracker has reported a 62.2 AutomationBench figure. Retain the discrepancy in the benchmark analysis. Do not treat 0.6 points as a meaningful advantage. CyberGym is a benchmark signal, not security certification or authority to test unapproved targets.

Primary source: https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash

## 3. Authority and file ownership

### Primary owned paths

| Path | Ownership |
|---|---|
| `packages/workflo-policy-go/` | Pure deterministic policy evaluation library |
| `security/threat-model/` | Assets, boundaries, threats, abuse cases, mitigations and owner map |
| `security/policies/` | Versioned policy examples, default profiles and policy fixtures |
| `security/adversarial-fixtures/` | Synthetic local attack/failure fixtures |
| `tests/security/` | Sandbox/runner/protocol/security acceptance tests |
| `tests/privacy/` | BYOK/metadata-only outbound payload assertions |
| `tests/chaos/security/` | Controlled failure, restart, lease, teardown and recovery cases |
| Policy library test package | Unit/property/fuzz tests for deterministic decisions |

Other code paths may be proposed as changes, but the owning agent implements the patch or explicitly reserves/assigns that exact file. Do not silently edit DeepSeek or GPT-6-owned source.

### Must not own

- Go CLI/runtime core or Go runner/Firecracker lifecycle.
- Command handlers/connectors/package distribution.
- FastAPI route/auth/database/RLS implementation.
- Dashboard/frontend.
- Canonical Pydantic schema, lifecycle, receipt or protocol semantics.
- Production secrets, signing private keys, customer data or live third-party targets.
- Final release approval or its own security review.

## 4. Core security principles

1. **Policy decision is deterministic.** The Go policy evaluator returns a typed allow/deny/reason decision and has no side effects.
2. **The model is not the policy engine.** A prompt, tool call or generated plan never grants a capability.
3. **Default deny.** Unknown operation, profile, provider origin, source behavior or data class is rejected unless explicitly admitted.
4. **Least capability.** Capabilities are narrow, run-scoped, attempt-bound, expiring and revocable.
5. **Host/guest separation.** Guest cannot access arbitrary host filesystem, shell, Docker socket, credentials or signer.
6. **Customer code remains customer-controlled.** Source, diffs, snippets, raw logs, environment values and secrets are prohibited from hosted prompts.
7. **Evidence is independent.** Guest report is untrusted input. Host probes and trusted verifier establish host and teardown claims.
8. **No fallback.** Strict production admission fails closed when Firecracker/KVM or any required boundary is unavailable.
9. **No claim inflation.** A passing unit test is not Gate B; a valid signature is not proof of defect-free software or verified cleanup.
10. **Authorized fixtures only.** All adversarial tests use synthetic local fixtures or explicitly authorized infrastructure.

## 5. Work packages

### MM-00 — Calibration and repository security audit

1. Record main SHA, model identifier, harness version, tool permissions and test environment.
2. Read ADR-0022/0024, M1 acceptance, Product Architecture, API Freeze, Quality Gates, AGENT Operating Model and runner/guest code.
3. Map trust boundaries: client, control plane, GitHub token broker, runner, Firecracker/jailer, kernel, cgroup, network, guest, tool gateway, provider gateway, evidence, receipt and dashboard.
4. Inventory host operations and existing enforcement code.
5. Inventory all inference egress paths, secrets and data classes.
6. Identify which current tests are unit, mocked, namespace/dev, integration or real KVM.
7. Identify tests that skip or misreport failures.

Deliverables:
- `MM-00-threat-and-boundary-map.md`;
- host operation allow/deny inventory;
- data-flow and egress inventory;
- security test coverage matrix;
- current security baseline with exact skips/blocks.

Acceptance: no code changes; every statement is linked to inspected source or a test result.

### MM-01 — Threat model and risk register

For each asset, record:
- asset owner;
- sensitivity and integrity requirement;
- trust boundary;
- attacker-controlled input;
- required capability;
- attack path/abuse case;
- likely impact;
- prevention/detection/recovery control;
- test ID;
- evidence location;
- residual risk;
- human acceptance requirement.

Minimum assets:
- user/session credentials;
- GitHub App installation grants and short-lived source tokens;
- runner workload identity and private key;
- RunSpec, policy and assignment;
- Firecracker/jailer process and kernel interfaces;
- guest disk and source snapshot;
- host/guest vsock messages;
- customer BYOK credential references;
- provider consent;
- test reports/logs/artifacts;
- receipt signer/trust anchors;
- tenant-owned records and evidence.

Acceptance: complete threat register with no unowned critical boundary; risks are explicit, not dismissed as “handled by container”.

### MM-02 — Go policy engine
Create a side-effect-free package in `packages/workflo-policy-go/`.

Policy evaluator inputs:
- versioned RunSpec/policy bundle;
- principal and tenant context as verified by control plane;
- profile ID/version and approved image digest;
- requested capabilities;
- resource request;
- source characteristics/manifest metadata;
- network class and dependency stage;
- requested Core/Deep/Security stage set;
- BYOK/hosted metadata consent state;
- artifact/output limits.

Policy decisions:
- `ALLOW` only when every required predicate is satisfied;
- `DENY` with stable typed reason code for unsupported or forbidden behavior;
- `INDETERMINATE/BLOCKED` when policy or required facts are missing.

The package must not:
- boot VMs;
- call the network;
- read secrets;
- invoke shell commands;
- change persistent state;
- call an LLM.

Decision output includes policy version/digest, evaluated inputs, permitted capability IDs, limits, expiry and explainable rejection codes. Sensitive input values must be omitted from explanations/logs.

Required submodules:
- schema/version validation;
- capability allowlist;
- source/path constraints;
- runtime/profile/image admission;
- resource ceilings and reservation rules;
- network/egress policy;
- test-stage authorization;
- output/evidence/artifact limits;
- inference endpoint/data-class policy;
- retention/consent checks;
- deterministic decision explanation.

Acceptance:
- table-driven coverage for every decision;
- negative tests for unknown values;
- fuzz/property tests for policy parsing and boundary values;
- same input gives same decision and policy digest;
- golden parity against accepted canonical contracts;
- no dependency on DeepSeek's host code.

### MM-03 — Sandbox adversarial fixture corpus

Build synthetic, repeatable fixtures:
- path traversal and archive extraction escape;
- absolute path and parent-directory references;
- symlink escape, hardlink ambiguity and nested repository;
- oversized archive, deep directory tree and too many files;
- malicious Git submodule/LFS behavior;
- hostile build/test config and lifecycle hooks;
- environment variable and credential discovery attempts;
- output flood, malformed test report and giant artifact;
- process tree/orphan attempt;
- CPU/memory/disk/PID exhaustion;
- unexpected DNS/IP/IPv6/redirect/proxy request;
- cloud metadata and local service access attempts;
- malformed, replayed and cross-attempt protocol messages;
- fake or missing teardown events;
- tampered source/evidence/receipt;
- prompt injection in README, comments, test output and HTTP body.

Every fixture specification contains:
- fixture ID and synthetic content;
- exact test harness;
- preconditions;
- attack stimulus;
- expected deny/terminate/block status;
- host-observed result;
- evidence artifact;
- whether real KVM is mandatory;
- owner of any failing fix.

Acceptance: deterministic, locally contained and safe to repeat in CI. No test sends traffic to arbitrary third-party targets.

### MM-04 — Filesystem, process and resource enforcement tests

Validate actual host/guest enforcement for:
- path/symlink/archive admission;
- no host filesystem mount to guest;
- no Docker socket or host IPC exposure;
- no ambient host credentials;
- privilege drop and capability boundaries;
- process count/PID ceiling;
- CPU quota and wall-clock timeout;
- memory limit and OOM behavior;
- disk quota and disk wipe/destroy semantics;
- stdout/stderr and evidence byte caps;
- child process termination and process-tree inventory;
- guest/VMM crash and supervisor restart.

Acceptance distinguishes:
- unit tests;
- fake/mocked process integration;
- dev namespace/bwrap;
- real Firecracker/KVM.

Only the last class satisfies production Gate B.

### MM-05 — Network and source boundary validation

Test:
- default-deny egress;
- explicit policy allowlist only;
- DNS rebinding and resolver behavior;
- IP literal, IPv4/IPv6, redirect and alternative protocol;
- metadata IP and link-local destinations;
- loopback, host gateway and private service access;
- proxy environment bypass;
- gateway/DNS failure;
- dependency preparation network separated from sealed test phase;
- GitHub source token host-only and removed before guest;
- source digest binding and immutable guest artifact;
- cross-run state/network separation.

Acceptance: actual network enforcement evidence on real KVM for strict mode. A mocked API response or unit test is supporting evidence only.

### MM-06 — Runner/guest protocol adversarial matrix

Test:
- unknown operation;
- unsupported major version;
- malformed schema;
- extra/unknown critical field;
- oversized frame;
- truncated frame;
- wrong run ID;
- wrong attempt ID;
- wrong sandbox ID;
- stale nonce;
- replayed sequence;
- out-of-order sequence;
- expired capability;
- revoked runner;
- stale claim generation/fencing token;
- guest asks for shell/host path/credential;
- guest reports false teardown success;
- disconnect during partial message.

Acceptance: fail closed with stable error; no arbitrary host action; no secret/attacker payload echoed into logs; host teardown remains independent.

### MM-07 — BYOK and metadata-only privacy validation

MiniMax owns security policy and outbound test oracle; GPT-6 owns backend business implementation; DeepSeek owns runner/tool transport.

Allowed hosted fields must be explicitly versioned/typed and limited to sanitized metadata such as categorical outcome, aggregate duration, coverage count or error category. The schema must not provide generic arbitrary prompt/body fields.

Forbidden data:
- source file bytes, snippets, diffs or repo archives;
- raw stdout/stderr/logs;
- full stack traces containing source or environment content;
- raw HTTP request/response bodies;
- Authorization headers, cookies, tokens, private keys, API keys;
- environment variables;
- customer personal data;
- unknown/free-form caller text;
- encoded/compressed representations of any prohibited class.

Test cases:
1. consent absent;
2. consent revoked or expired;
3. organization policy denies hosted prompts;
4. per-run opt-in missing;
5. source canary nested in allowed-looking metadata;
6. secret canary in logs/header/body;
7. encoded/normalized canary;
8. overlong/deep payload;
9. unknown fields;
10. arbitrary endpoint/origin;
11. provider 401/429/5xx/timeout;
12. direct cloud route bypass;
13. provider gateway unavailable;
14. model returns malformed or tool-like output;
15. credential value appears in exception.

Acceptance:
- inspect the actual serialized outbound request in a controlled test environment;
- only allowlisted values present;
- no consent means no request;
- consent cannot widen payload schema;
- no retry to an alternate direct provider;
- no source/secret canary leaves customer boundary;
- if proof is incomplete, hosted prompts remain disabled.

### MM-08 — AI agent and tool authorization tests

The planner proposes. Deterministic policy authorizes each action.

Test:
- prompt injection in repository README, comment, test name, application response, logs and issue text;
- model asks for unknown tool;
- invalid, missing or extra tool argument;
- path outside source root;
- another run/tenant resource identifier;
- arbitrary URL or network target;
- model asks to increase its own permission;
- repeated non-idempotent action;
- tool-call loop and plan depth exhaustion;
- token/time/call/output budget exhaustion;
- test generation tries to modify original source;
- model output contains secret-like data;
- ToolGateway unreachable;
- cancellation while tool is running.

Acceptance: no model text is interpreted as permission; each tool call checks current policy and attempt binding; budgets are hard limits, not prompt suggestions.

### MM-09 — Teardown, receipt and evidence adversarial suite

For every attempt, define expected resource inventory before launch:
- Firecracker process;
- jailer process/scope;
- cgroup;
- network namespace/interface/rules;
- vsock/listener/socket;
- VM disk/workspace;
- temporary credential and source acquisition workspace;
- child processes and temp artifacts.

Test partial provisioning, failed boot, guest crash, VMM crash, host process restart, shutdown timeout, force kill, disk destroy failure, cgroup cleanup failure, namespace leak, socket listener leak, stale credential and incomplete evidence.

Receipt/evidence tests:
- valid receipt and trust anchor;
- wrong key;
- modified receipt bytes;
- duplicate JSON keys;
- wrong source SHA;
- wrong attempt/sandbox binding;
- missing evidence object;
- changed artifact hash;
- missing/unknown teardown check;
- receipt says tmpfs unmount when only host deletion occurred;
- replayed receipt across run/attempt;
- old v1-v4 reader compatibility.

Acceptance: no `VERIFIED_CLEAN` result unless every required host-observed check passes; failed or unobservable teardown must produce explicit invalid/incomplete/not-verified trust state.

### MM-10 — Security gate contract for four language profiles

Design the later customer Security testing gate as a separate stage:
- Python: dependency/SAST/config/secrets/authorization and FastAPI profile checks;
- Node: package/dependency/secret/config/Express middleware and auth checks;
- Go: module/dependency/static/config/HTTP auth checks;
- Java: Maven/Gradle dependency/static/config/Spring authorization checks.

For each profile pin tool version, scanner/image digest, ruleset version, command argv, timeout, network class, output parser and evidence type. Do not create profile-specific host privileges.

Acceptance: test profiles report their own status and findings. Scanner unavailable or profile unsupported returns BLOCKED/ERROR/SKIPPED—not PASS.

### MM-11 — Independent security review and disposition
For each DeepSeek, GLM and GPT-6 implementation PR touching security-relevant paths:
1. inspect exact base/head SHA and file inventory;
2. map diff to threat model and accepted ADR;
3. run assigned negative tests;
4. inspect failure/skip results;
5. verify no false-green CI;
6. report findings by severity and reproduction;
7. nominate fix owner;
8. re-test after patch;
9. require human approval for high/critical and policy-boundary changes.

Severity rubric:
- Blocker: source/secret disclosure, host escape, data loss, false trusted receipt;
- Critical: fail-open strict boundary, tenant isolation bypass, signer/key compromise;
- High: incorrect admission/lease/evidence/teardown behavior;
- Medium: bounded functional or policy defect;
- Low: clarity/maintainability issue without trust impact.

MiniMax does not self-approve its policy code or adversarial suite.

### MM-12 — Release security evidence pack
Produce:
- threat model and data-flow map;
- policy version/digest;
- security test manifest;
- fixture inventory;
- real KVM report;
- source/credential egress proof;
- network enforcement report;
- resource/teardown report;
- protocol attack matrix;
- privacy outbound payload trace with synthetic data;
- vulnerability report and dispositions;
- residual risk and human sign-off record.

## 6. Mandatory collaboration contracts

| Partner | Provide | Receive |
|---|---|---|
| DeepSeek | host operation registry, cgroup/network/teardown probes, protocol types | policy API, test fixture IDs, failure oracles, adversarial PR review |
| GPT-6 | API auth principals, consent model, runner endpoints, audit fields | API negative tests, privacy payload test suite, RLS/test findings |
| GLM | CLI flags, connector behavior, profile metadata, package integrity paths | malicious manifest fixtures, permission rules, connector security test cases |
| Gemini | UI states for blocked/revoked/incomplete/trust failure | precise status semantics and no-false-green UX test cases |

## 7. Test environment and permissions

- Use isolated synthetic repositories and fixtures.
- Do not scan arbitrary public/private third-party targets.
- Do not read real production secrets or customer data.
- Use test credentials with narrow scope and short expiry.
- Do not run untrusted fixtures directly on the host.
- KVM acceptance uses explicitly authorized owner-controlled host.
- Mock tests must be labelled as mocks and cannot satisfy Gate B.
- No change to security baseline or CI requiredness without human owner review.

## 8. Definition of done

The policy evaluator is deterministic and parity-tested; every required sandbox/runner boundary has positive and negative tests; the real KVM matrix proves actual isolation and teardown; hosted-prompt tests inspect the actual serialized payload; no critical/high finding remains unresolved without explicit owner risk acceptance; and every security statement is linked to a specific commit, test and artifact.
