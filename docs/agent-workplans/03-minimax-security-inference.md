# Agent 03 — MiniMax M3.1 Flash: Security, Privacy and Inference

**Role:** Application security and model-integration engineer  
**Branch:** `agent/minimax-security-inference`  
**Primary owner:** MiniMax M3.1 Flash  
**Reviewers:** DeepSeek (worker integration), GPT-6 Luna (test verification), human security owner (approval)

## 1. Why this model owns this work

MiniMax's M3.1 Flash general-availability page reports:

- DeepSWE v1.1: **73.7%**
- CyberGym: **82%**
- AutomationBench-AA: **62.2**
- Agents' Last Exam: **29.6**
- OSWorld V2: **61.7**

MiniMax describes cybersecurity use cases as code auditing, vulnerability patching, penetration testing, malicious-code analysis and reverse engineering. The page explicitly cautions that model output is assisted analysis and should be decided using independent evidence.

Source: https://code.minimax.io/tools/m3.1-flash

The 82% CyberGym score is a vendor-published benchmark claim, not a certification, proof of security or replacement for human review.

## 2. Owned paths

Primary:

- `apps/control-plane/app/api/v1/inference.py` and inference-specific supporting modules.
- `apps/worker-engine/src/workflo_worker/model/` — model client and worker-side integration security.
- `workflo-ai-integration/` — existing router/safety-gate code, subject to approved consolidation.
- Dedicated inference, privacy, prompt-injection and adversarial test suites.

Do not modify:

- Firecracker host manager and guest lifecycle owned by DeepSeek.
- CLI architecture owned by GLM.
- Dashboard owned by Gemini.
- Canonical receipt/lifecycle schema without approval.
- Release gates to make incomplete model acceptance pass.

## 3. Mission

Prove the model cannot exceed the capabilities Workflo grants it and prove the hosted provider receives only explicitly authorized, schema-validated, sanitized metadata—not source code, credentials, raw logs or arbitrary prompts.

The model is a planner, not an authorization authority.

## 4. Work packages

### MM-01 — Complete inference-path inventory (Days 1–3)

Search the entire repository, not only the known gateway, for:

- OpenAI-compatible clients and `chat/completions` calls.
- `base_url`, API keys and direct provider configuration.
- planner/model adapters.
- environment variables injected into worker/guest.
- retry, fallback and response parsing logic.
- prompt assembly and observation serialization.

Build a data-flow table: caller -> process -> fields -> destination -> credentials -> persistence/logging -> authorization.

**Acceptance:** every real and test inference path is classified as local, hosted-gateway, direct/blocked, mock or legacy. Identify every bypass and reachable call site.

### MM-02 — Enforce inference modes (Days 3–7)

- Local inference: worker-owned pinned llama.cpp process, loopback-only.
- Hosted inference: only via the control-plane privacy gateway.
- Strict execution must not permit the direct CLI planner path or standalone direct cloud client.
- Remove direct-mode defaults from strict execution; do not delete compatibility code without proving callers.
- No arbitrary user/run-spec supplied provider URL.
- Provider keys remain outside guest and client configuration in hosted mode.
- Gateway outage, bad configuration or privacy failure stops hosted inference; no silent direct or alternate-provider fallback.

**Acceptance:** repository-wide tests prove there is no supported strict-profile route from source-bearing guest data directly to a provider.

### MM-03 — Define allowlisted observation contract (Days 4–9)

Use explicit versioned schemas. Start with a deny-by-default field inventory. A field is permitted only after a data-owner review.

Potential fields, only when normalized and approved:

- bounded HTTP status codes;
- coarse timing buckets;
- normalized route template if non-sensitive;
- predefined test/assertion identifier;
- approved error category;
- small bounded counters.

Reject by default:

- source code or file contents;
- raw request/response body;
- headers, cookies, auth material;
- environment variables;
- command output;
- full application logs;
- stack traces containing paths/values;
- repository metadata that reveals secrets;
- free-form user mission text unless separately sanitized and authorized.

The gateway must build the provider prompt itself. Callers must not submit raw prompts or additional fields.

**Acceptance:** schema rejects unknown fields; payload inspection tests prove only approved fields can be serialized upstream.

### MM-04 — Secret and source rejection (Days 7–12)

- Add detectors for common token/key formats, private-key blocks, credentials and sensitive headers.
- Use rejection for uncertain or high-risk payloads; redaction alone is not sufficient for every field.
- Treat logs, HTTP output, repository text and model output as untrusted.
- Bound nested JSON, string length, array length and total serialized bytes.
- Prevent encoding/normalization tricks from bypassing inspection.
- Keep outbound payload capture in test harness only; do not retain customer source or secrets in production diagnostics.

**Acceptance:** positive and negative test fixtures for literal, encoded, nested, multiline and split-field secret/source material. The real outbound request must be inspected in a controlled staging test.

### MM-05 — Prompt injection and agent authority (Days 9–15)

- Build fixtures for malicious README, issue text, source comments, logs and HTTP responses.
- The system prompt is policy, not a security boundary.
- Treat all repository/application content as untrusted observations.
- Model proposes typed tool plans only.
- ToolGateway independently authorizes every tool, target, path, method, body size and call budget.
- No shell, arbitrary network, external file read, credential access, cross-run or host action.
- Refuse unknown tools and invalid/extra arguments.
- Do not allow model-generated text to change the run policy.

**Acceptance:** injection fixture cannot add a tool, expand network scope, read source outside the allowlist, or alter authorization.

### MM-06 — Response validation and resource budgets (Days 12–18)

- Strict JSON/schema validation; reject prose, malformed or partial response where structured output is required.
- Validate tool name and argument schema before ToolGateway call.
- Enforce max tool calls, plan steps, rounds, input/output tokens, response bytes, wall time and provider cost.
- Enforce per-run and per-tenant budgets.
- Bound retries; do not repeat non-idempotent tool calls automatically.
- Record model ID/version, prompt schema version, request counts, timing, token counts and error class—never raw prompts or source.

**Acceptance:** malformed, excessive, repeated, unauthorized and time-exceeded plans are rejected with deterministic error classes.

### MM-07 — Local model artifact integrity (Days 14–20)

- Follow `P4_ACCEPTANCE.md` exactly: pinned llama.cpp image digest, frozen model identity, base GGUF and named adapter hashes.
- Reject absent, additional or changed adapters.
- Verify paths and hashes before starting server.
- Bind model/image IDs and hashes into provenance.
- Model server listens on loopback only; no published port or guest egress.
- Validate generated test path, schema, syntax/AST/compile and overwrite policy.
- On model error or teardown uncertainty, fail closed.

**Acceptance:** real artifacts and digest-pinned image pass the existing Gate 4 workflow; mock tests do not count as Gate 4.

### MM-08 — Real protected inference acceptance (Days 18–25)

Coordinate with GPT-6 Luna on test result collection and DeepSeek on worker integration. Run existing Gate 5 workflow only after required real artifacts, protected runner and secrets are ready.

Required cases include:

- valid authorized observation request;
- unauthorized and source-bearing request denial;
- wrong/missing key;
- model timeout and transport failure;
- model response schema failure;
- repeated request/cross-run separation;
- concurrency 1, 2 and 4;
- rollback to prior immutable model/image;
- teardown of process, listeners, container and cache;
- metadata-only receipt/provenance.

**Acceptance:** protected staging run passes on exact candidate SHA and separate verifier validates receipt/evidence and rejects tampered identities.

### MM-09 — Security report and handoff (Days 25–30)

Deliver threat model updates, data-flow diagram, allowlist schema, test corpus and results, all known bypasses, residual risks and recommendation on whether hosted/local AI features can be beta-enabled.

## 5. Mandatory adversarial matrix

- Direct API bypass.
- Prompt injection in repository files and application responses.
- Source content hidden in logs, error, route, path or tool arguments.
- Secret in JSON, nested object, headers, Unicode and encoded strings.
- Oversized/deeply nested observations.
- Model returns extra fields, unknown tool, invalid args or malformed JSON.
- Model asks to expand permissions.
- Model tries external network/host path/credential access.
- API key error, quota, timeout, 5xx, malformed response.
- Gateway down.
- Model server listens on non-loopback.
- GGUF or adapter hash mismatch.
- Model process fails to stop.
- Concurrent requests attempt to cross-contaminate state.

## 6. Stop conditions

Do not enable hosted inference if any route can send raw source, if schema validation is permissive, if outbound payload inspection is absent, if credentials enter the guest, or if a direct bypass remains reachable in the strict profile.

Do not call a model output a confirmed vulnerability. Security findings need reproducibility and independent validation. MiniMax is not the security sign-off authority.
