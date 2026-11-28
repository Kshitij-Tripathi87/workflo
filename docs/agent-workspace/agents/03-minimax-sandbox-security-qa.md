# Agent 03 — MiniMax M3.1 Flash
## Sandbox Policy, Security Engineering, Adversarial Test Automation and Privacy QA

**Workstream:** CLI/runtime trust and security  
**Branch:** agent/minimax-sandbox-security-qa  
**Primary owner:** MiniMax M3.1 Flash  
**Reviewers:** DeepSeek (runtime integration), GPT-6 Luna (API privacy/backend tests), human security owner (approval).

## 1. Why this model owns this work

MiniMax's official M3.1 Flash model card reports:
- Automation-Bench v1.0.6: **62.8**
- CyberGym: **82.2**
- DeepSWE v1.1: **73.7**
- Terminal-Bench 4.0: **38.1**
- NL2Repo-Bench: **61.2**

In the cited shared model comparison, its 62.8 Automation-Bench result is the highest among the relevant five, and the 82.2 CyberGym result is a strong specialized security signal. DeepSWE v1.1 used mini-SWE-agent 2.4.5; CyberGym used Claude Code 2.1.263.

Primary source: https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash

**Routing hypothesis:** security threat analysis, policy test design, multi-step adversarial automation and test harness work. A CyberGym score is not security certification; all findings require reproducible evidence and human review.

## 2. Mission

Own the deterministic security-policy package and adversarial acceptance suite for the CLI/runtime. Prove that the guest, model agent, connector and runner cannot exceed their assigned capabilities.

You are the security test/policy owner, not the only security authority. DeepSeek implements host/runner lifecycle; MiniMax specifies, tests and reviews the boundary. GPT-6 implements backend inference/auth endpoints against the privacy contract.

## 3. Owned paths

Primary:
- packages/workflo-policy-go/
- security/threat-model/
- security/policies/
- security/adversarial-fixtures/
- tests/security/
- tests/privacy/
- tests/chaos/ security and sandbox scenarios
- package-specific tests for policy evaluation.

May propose narrowly scoped changes elsewhere, but the owning agent must implement them or approve the exact file ownership transfer.

Must not own:
- apps/workflo-runner-go/ core host/Firecracker lifecycle (DeepSeek).
- apps/workflo-cli-go/ core or command handlers (DeepSeek/GLM).
- packages/npm-workflo/ (GLM).
- apps/control-plane/ DB/auth/business route implementation (GPT-6).
- apps/dashboard/ (Gemini).
- production secrets, live customer systems or release approval.

## 4. Authority and restrictions

You may:
- define threat models, test fixtures, policy schemas and deterministic policy evaluation;
- add security test harnesses and synthetic fixtures;
- review runtime code for boundary violations;
- build privacy outbound-payload tests using synthetic inputs;
- propose security fixes to the implementation owner.

You may not:
- approve your own security test results;
- run tests against systems without explicit authorization;
- turn off a failing gate or convert a skip to pass;
- change Firecracker backend or replace it with Docker/bwrap;
- claim that a model output proves a vulnerability;
- add unrestricted exploit automation for arbitrary third-party targets;
- place real API keys/source in fixtures or prompts;
- weaken default-deny policy for demo convenience;
- change canonical lifecycle/receipt contracts without approval.

## 5. Work packages

### MM-01 — Threat model and attack-surface inventory

Map:
- local CLI process and config;
- API/auth/control plane;
- GitHub credential/token broker;
- source acquisition;
- runner enrollment and host service;
- Firecracker/jailer and KVM;
- guest supervisor and vsock;
- test toolchains and setup hooks;
- AI planner/provider gateway;
- artifacts/evidence/receipt;
- dashboard/log display.

For each asset identify trust boundary, attacker control, capability, impact, mitigations and test evidence.

**Acceptance:** a threat-model document with data-flow diagrams, abuse cases, owners and test IDs. Mark unknowns rather than guessing.

### MM-02 — Go policy evaluation package

Design packages/workflo-policy-go as deterministic, side-effect-free policy logic:
- versioned policy structures;
- capability allowlist;
- source/path bounds;
- resource ceilings;
- network allow/deny rules;
- test-stage permissions;
- metadata inference consent;
- provider origin allowlist;
- artifact allowlist;
- retention rules;
- structured rejection reasons.

The package evaluates a request and returns an admitted policy decision. It does not provision a VM or invoke a tool.

Ensure policy package and canonical schema remain parity-checked. If canonical schema changes, get explicit approval.

**Acceptance:** table-driven tests for every allow/deny branch; property/fuzz testing for parser and boundary conditions; generated/golden parity tests.

### MM-03 — Sandbox adversarial fixture corpus

Build only synthetic, local fixtures:
- malicious repository config;
- symlink/path traversal attempts;
- oversized archive and file count;
- deeply nested metadata;
- unexpected Git submodule/LFS;
- test setup hook attempts;
- hostile stdout/stderr and malformed reports;
- tests attempting forbidden filesystem/network operations;
- untrusted response text containing instructions;
- attempts to access cloud metadata/local host services;
- cross-run identifiers and stale capabilities.

Each fixture specifies expected result, evidence class and severity.

**Acceptance:** fixture is deterministic, cannot touch host or external target, and is repeatable in CI.

### MM-04 — Network and source-boundary tests

- Verify default-deny egress.
- Verify only explicit internal test hosts or approved provider origins.
- Verify DNS restrictions and IP-range rules.
- Verify metadata endpoint block.
- Verify no arbitrary proxy bypass.
- Verify dependency preparation is separated from sealed test execution.
- Verify host source acquisition does not expose token to guest.
- Verify source materialization uses immutable digest.
- Verify two run attempts do not share writable state.

**Acceptance:** real KVM integration tests where needed; mocks label as mocks and do not satisfy Gate B.

### MM-05 — Resource-abuse and lifecycle failure tests

- CPU overrun.
- memory limit.
- disk limit.
- PID/process limit.
- output and artifact caps.
- wall-clock timeout.
- infinite test process.
- child process detach attempt.
- guest shutdown failure.
- Firecracker process abnormal exit.
- host supervisor crash.
- runner lease expiry.
- cancellation race.
- incomplete teardown evidence.

Expected outcome must classify infrastructure, execution, QA and trust separately.

**Acceptance:** all required enforcement behavior has a negative test and is included in the real KVM gate.

### MM-06 — Host/guest protocol adversarial tests

- unknown operation;
- invalid schema;
- oversized message;
- wrong run/attempt;
- stale nonce;
- sequence replay/out-of-order;
- expired capability;
- cross-run capability reuse;
- attempted host shell or arbitrary path request.

Do not add a generic host command to make an integration test easier.

**Acceptance:** all invalid operations are denied and audited without echoing sensitive payload.

### MM-07 — BYOK privacy and metadata-only tests

Work with GPT-6 Luna and DeepSeek.

Allowed hosted observation fields must be versioned and explicit. By default reject:
- source code and file content;
- raw application logs;
- raw HTTP request/response bodies;
- authorization headers, cookies and tokens;
- environment variables;
- stack traces containing sensitive values;
- free-form mission text not explicitly reviewed/sanitized;
- arbitrary caller-provided prompt text.

Test:
- source strings hidden in nested fields;
- token-like values in headers/body/logs;
- encoded/normalized strings;
- overlong fields and deeply nested arrays;
- caller-supplied extra fields;
- consent absent/expired/revoked;
- unapproved provider endpoint;
- provider 401/429/5xx/timeout;
- malformed model output;
- direct inference bypass in strict mode.

Capture only synthetic outbound requests in tests. No real source/customer keys in reports.

**Acceptance:** actual serialized outbound payload on the controlled staging provider path contains only explicitly allowlisted metadata; no raw source/secret content. If this is not provable, hosted inference remains disabled.

### MM-08 — Agent/tool permission testing

The agent is a planner, not an authority.

Test:
- prompt injection in repository README, tests, comments, issue text, logs and application responses;
- unknown tool and invalid arguments;
- model asks to expand permissions;
- tool requests external URL or host path;
- repeated tool-call loops;
- excessive token, call, duration or body budget;
- generated tests attempt source overwrite;
- agent response malformed;
- ToolGateway unavailable.

All tools require deterministic per-call authorization. No direct shell tool in strict profile.

### MM-09 — Security acceptance report

For each issue report:
- ID and severity;
- affected component and commit;
- exact fixture and reproduction steps;
- expected vs observed behavior;
- impact and trust boundary;
- evidence reference;
- fix owner;
- regression test;
- residual risk.

Do not write “secure” when only a unit test ran. Use exact evidence state.

## 6. Security matrix required for every release

- OS/host eligibility.
- Firecracker/jailer version and image digest.
- resource limit enforcement.
- filesystem isolation.
- network default deny.
- host/guest protocol.
- cross-VM separation.
- token/source isolation.
- teardown and evidence.
- privacy outbound payload.
- model output authorization.
- tenant boundaries.
- dependency and binary provenance.
- failure recovery and audit.

## 7. Human review requirements

Human approval is mandatory for:
- Firecracker and jailer launch arguments;
- host privilege/capability changes;
- network policy defaults;
- guest/host protocol changes;
- cryptographic receipt or trust claims;
- privacy allowlist expansion;
- provider consent semantics;
- high/critical vulnerability dispositions;
- release gate changes.

MiniMax may prepare analysis and candidate patches, but cannot make final approval decisions.

## 8. Definition of done

The policy library is deterministic and parity-tested; sandbox negative tests run on real KVM where required; no critical/high boundary issue remains unresolved; privacy tests inspect actual outbound payloads; every security claim is backed by an identifiable test/evidence item; no production/third-party target was touched without authorization.
