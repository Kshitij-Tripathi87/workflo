# Workflo Trust MVP — Threat Model and Security Test Plan v1

**Status:** Proposed  
**Method:** Asset inventory -> trust boundaries -> abuse cases -> controls -> tests  
**Security objective:** contain hostile repository code, preserve tenant boundaries, prevent agent privilege expansion, and make evidence claims independently verifiable.

This is a defensive engineering plan, not a claim that the platform is immune to attack. No product can guarantee that an experienced attacker cannot find a vulnerability.

---

## 1. Security objectives

1. Repository code is treated as hostile input from the moment it enters the runner.
2. Guest compromise must not provide host, control-plane, signing-key, or cross-tenant access.
3. Agent/model output must never create authority or bypass deterministic policy.
4. A user or runner must access only its authorized organization, project, run, attempt, and artifacts.
5. Source code and secrets must not leak to hosted model providers or Workflo control-plane storage by default.
6. Evidence tampering, replay, cross-run reference, and false teardown claims must be detected.
7. A missing security mechanism causes explicit rejection or unknown trust state, never a silent downgrade.
8. Operations are affordable without a paid security or observability platform.

---

## 2. Assets and security requirements

| Asset | Impact if compromised | Protection |
|---|---|---|
| Repository source | IP theft, customer breach | Customer-side acquisition/execution; no source upload |
| GitHub installation/API credential | Repo read/write compromise | Minimum scopes, short-lived tokens, host-only use, rotation |
| Model provider key | Unauthorized spend and data access | Host-side secret, BYOK, no guest mount, no logs |
| Tenant records | Cross-customer data disclosure | PostgreSQL RLS, composite scope checks, authorization |
| Run policy | Unauthorized command/network/capability | Immutable bundle and digest binding |
| Runner lease | Unauthorized execution or result spoofing | Scoped capability, expiry, fencing token, replay protection |
| Guest VM | Host/tenant escape | Firecracker/jailer, seccomp, namespaces, cgroups, no host mounts |
| Agent tools | Privileged action or exfiltration | Fixed allowlist, schema and policy validation |
| Model artifacts | Malicious or tampered behavior | Digest-pinned manifest, provenance and acceptance gates |
| Evidence bundle | False audit or trust claim | Canonical hashing, append-only ledger, scope validation |
| Receipt signing key | Forged receipts | Host-side signer, no guest access, key rotation |
| Webhook/event stream | Forged or replayed run | HMAC validation, delivery deduplication, idempotency |
| CI/build chain | Compromised release | Pinned actions/dependencies, branch protection, review and tests |

---

## 3. Attacker profiles and assumptions

- **Malicious contributor:** controls a branch or pull request in a connected repository.
- **Compromised dependency:** install/build script attempts filesystem, network, or process abuse.
- **Prompt injector:** places instructions in source comments, README, issue descriptions, web pages, test outputs, or generated files.
- **Malicious tenant user:** has valid access to one organization and seeks another organization's data or authority.
- **Credential thief:** obtains a user, runner, GitHub, or model credential.
- **Compromised guest:** achieves code execution inside the test VM and attempts to cross the guest/host boundary.
- **Event replayer:** reuses a webhook, run request, runner lease, event, or approval.
- **Supply-chain attacker:** compromises a package, base image, model file, workflow action, or build artifact.

Assume guest code can execute arbitrary instructions inside the guest. Do not rely on guest honesty for lifecycle or teardown claims.

---

## 4. Trust boundaries

### TB-1: GitHub / external input -> control plane
Untrusted PR data and event payloads become validated metadata. No external string is treated as a command or file path.

### TB-2: control plane -> runner host
Only a scoped, signed, expiring assignment is delivered. It binds org, project, run, attempt, source commit, policy digest, limits, and expiry.

### TB-3: runner host -> guest
Only a source snapshot, immutable policy, approved test configuration, and a narrow typed protocol cross the boundary. Host credentials and signing keys do not cross it.

### TB-4: guest -> host evidence collector
Guest output is untrusted. It is size-capped, parsed against strict schemas, tagged as guest-observed, and never allowed to claim host teardown or signing success.

### TB-5: guest / host -> model provider
Hosted requests pass through a host privacy gateway. Local inference remains in the customer boundary. Model output is untrusted.

### TB-6: control plane -> database
Every tenant-scoped transaction uses a verified tenant context and a runtime role that cannot bypass RLS.

### TB-7: evidence service -> signer
Only a fully validated receipt payload is eligible for signing. The signer cannot mutate run findings or infer missing evidence.

---

## 5. Abuse cases and mitigations

| ID | Abuse case | Prevention / detection | Required regression test |
|---|---|---|---|
| WTM-01 | Malicious PR executes a host command | Guest VM; no host shell API; host/guest protocol allowlist | Guest attempts unsupported host operation; denied |
| WTM-02 | Guest reads signing key | Signing key outside guest and ordinary worker | Search guest mounts/env/process for signer material; none present |
| WTM-03 | Guest reaches cloud metadata endpoint | Egress default deny; host network policy | Metadata IP, link-local, private IP and redirect fixtures denied |
| WTM-04 | Dependency script exfiltrates source | Offline or controlled registry proxy; no direct guest egress | Build fixture attempts arbitrary egress; blocked |
| WTM-05 | Path traversal writes outside workspace | Canonical path validation, root confinement, symlink checks | ../, absolute path, symlink chain, hardlink and special-file tests |
| WTM-06 | Prompt injection grants a tool | Tool allowlist and policy engine are external to LLM | README/comment/test output says ignore policy; no permission change |
| WTM-07 | Model emits arbitrary command | Strict typed plan schema; no shell tool | Unknown tool, malformed args, extra keys rejected |
| WTM-08 | Model hallucination becomes verified failure | Deterministic judge requires reproducible evidence | Model-only assertion remains candidate/inconclusive |
| WTM-09 | Hosted provider receives source | Metadata-only request schema and host privacy gateway | Canary source string in every request field; gateway rejects |
| WTM-10 | Model API key leaks to guest/log | Host-side secret and redaction | Inspect environment, artifacts, logs, guest filesystem |
| WTM-11 | Tenant A reads Tenant B run | RLS plus application authorization | Cross-tenant list/get/export/joins all return denied/empty |
| WTM-12 | RLS bypass via owner connection | Runtime role non-owner/non-superuser/no BYPASSRLS | Startup rejects unsafe database role; test role attributes |
| WTM-13 | Missing tenant context returns all rows | Default-deny RLS and transaction-local context | No org context: read/write denied |
| WTM-14 | IDOR by guessed run ID | Every route checks org/project membership | Valid ID from another org denied on all endpoints |
| WTM-15 | Duplicate PR event creates duplicate run | Idempotency key and delivery dedupe | Re-submit same event/key returns original run |
| WTM-16 | Stale runner completes replaced lease | Fencing token and attempt binding | Expired lease with old token rejected |
| WTM-17 | Event replay changes run state | Sequence and producer-authority validation | Guest lifecycle event cannot transition product state |
| WTM-18 | Event payload tampering | Canonical digest and hash chain | Mutated event/sequence/prev_hash rejected |
| WTM-19 | Receipt altered after signing | Signature and factual binding checks | Change result, source SHA, policy digest or teardown record; verify fails |
| WTM-20 | Cross-run evidence reference | Scope validator | Artifact from other run/attempt/tenant rejected |
| WTM-21 | Teardown falsely reported clean | Host-observed verifier, not guest report | Kill VM / leave mount / leave process; trust not clean |
| WTM-22 | Runner resource exhaustion | CPU, memory, disk, process, wall-time, output and token caps | Stress fixture reaches cap; run terminates with explicit outcome |
| WTM-23 | SSRF through probe URL | Host/IP allowlists, DNS resolution, redirect checks, network egress | Loopback, private, metadata, alternate IP and redirect tests denied |
| WTM-24 | Webhook spoof | HMAC-SHA256 over raw request body | Invalid signature, body mutation, missing secret rejected |
| WTM-25 | Webhook replay | Delivery ID uniqueness and event state | Same X-GitHub-Delivery is processed once |
| WTM-26 | Credential overpermission | GitHub App least privilege, branch/read permissions | Inspect installation permissions and deny write actions |
| WTM-27 | Mutable model/runtime artifact | Digest-pinned manifests and image identities | Missing, extra, wrong-hash, mutable tag fail closed |
| WTM-28 | CI workflow compromise | Pinned actions, protected branches, review | Unpinned action or unauthorized workflow change fails policy |
| WTM-29 | Secret in logs/artifacts | Structured redaction and metadata-only evidence | Canary secrets in stdout/stderr/events; verify absent |
| WTM-30 | Unbounded agent loop | External iteration/time/token/call quotas | Planner repeats tool call; hard stop and audit event |

---

## 6. Security design requirements

### 6.1 Identity

- Separate human, CI, runner, and internal service identities.
- API keys are stored as hashes; refresh/session tokens are rotated and revocable.
- Runner capability is short-lived and scoped to one org/project/run/attempt/policy digest.
- Every privileged operation is checked server-side.
- Avoid broad personal access tokens for GitHub automation.
- Never put bearer credentials in URLs or model prompts.

### 6.2 Database

- Use PostgreSQL for multi-tenant pilot data.
- Apply RLS to all tenant-owned tables.
- Use FORCE ROW LEVEL SECURITY where appropriate.
- Runtime DB principal is not owner, superuser, or BYPASSRLS.
- Tenant context is transaction-local.
- Use composite tenant foreign keys and negative tests.
- Audit administrative bypasses.
- Do not use SQLite to claim RLS protection.

### 6.3 Guest runtime

Production untrusted-repo execution must use the accepted Firecracker boundary:
- KVM verification at runner startup and admission.
- Pinned Firecracker and jailer versions/artifacts.
- Dedicated nonprivileged UID/GID.
- Jailer, seccomp, cgroups, namespaces, resource caps.
- Host paths and parent directories not writable by unprivileged users.
- No Docker socket or broad host mount.
- Guest root filesystem immutable; writable overlay ephemeral.
- Guest-host communication only by typed vsock messages.
- Network deny by default.
- Host-observed teardown and resource-removal verification.
- Regular patching of host and guest kernels, Firecracker, jailer, and microcode as applicable.

Docker and bwrap are development/CI tools until the production runtime gate is passed.

### 6.4 Agent runtime

- No general-purpose shell tool.
- Tools are registered by code, not model output.
- Every tool has a schema, capability name, policy binding, maximum input/output size, timeout, and audit event.
- Tool schemas are versioned and hashed.
- All untrusted text is quoted/classified as data; system policy comes from code/config outside repository content.
- Model output is a proposal; code validates schema, semantics, tenant, paths, network and budgets.
- No chain-of-thought capture.
- Candidate and verified finding categories are distinct.

### 6.5 Signing and evidence

- Guest cannot sign or choose signer identity.
- Evidence service checks artifact digest, scope, chain, policy, source identity, results, and teardown before constructing receipt.
- The signer receives only a validated canonical payload.
- Dev signer is forbidden in production.
- Independent verifier runs without access to producer secrets.
- Receipt limitations remain explicit.

### 6.6 Privacy

- No source archive in control-plane database or object store.
- No raw prompt/response bodies persisted.
- Hosted provider route rejects source and secret data.
- Customer-owned local inference is used for source-aware tasks.
- Customer BYOK does not change source privacy policy.
- Redaction is tested with canary values.

### 6.7 Webhooks and integrations

Initial phase uses Actions/CLI. When GitHub App support exists:
- Subscribe only to minimum events.
- Verify raw-body HMAC-SHA256 signature.
- Use HTTPS and verify TLS.
- Check event type and action.
- Deduplicate delivery ID.
- Respond quickly, enqueue work, process asynchronously.
- Use narrow App permissions.
- Keep credentials out of payload URLs/logs.

### 6.8 Secure development lifecycle

- Pull request review for auth, policy, execution, evidence, dependencies, model, and workflows.
- Automated unit, integration, adversarial, type, lint, secret, dependency, and container checks.
- Dependency lockfiles and pinned CI actions.
- Release image and model digest identity.
- Reproducible build metadata where practical.
- Security issues tracked with severity and remediation owner.
- Threat model updated when a new trust boundary or tool is introduced.

---

## 7. Severity and release policy

| Severity | Example | Release rule |
|---|---|---|
| Critical | Cross-tenant read, host escape, signer compromise, source exfiltration | Block release; incident/credential rotation if live |
| High | Guest egress bypass, RLS bypass, forged clean receipt, auth bypass | Block strict profile |
| Medium | Missing audit event, weak rate limit, UI authorization mismatch | Fix before pilot or explicitly scope/mitigate |
| Low | Non-sensitive UI issue, low-impact telemetry gap | Track and prioritize |

A run must report trust as unknown or failed when evidence is incomplete. Do not convert a security failure into a QA pass.

---

## 8. Security acceptance checklist

### Before a private design-partner pilot
- [ ] Threat model reviewed.
- [ ] Customer-owned runner install documented.
- [ ] No source uploaded to control plane.
- [ ] Runtime profile clearly labeled.
- [ ] API keys scoped, hashed, rotated and revocable.
- [ ] Tenant RLS and cross-tenant tests pass.
- [ ] Agent allowlist and prompt-injection tests pass.
- [ ] Hosted model path disabled or metadata-only gateway proven.
- [ ] Evidence and signature tamper tests pass.
- [ ] Host teardown checks and incident runbook exist.

### Before any untrusted repository execution
- [ ] Actual Firecracker/KVM Gate B passes.
- [ ] Jailer, seccomp, cgroups, namespaces and dedicated identity verified.
- [ ] Egress default-deny tests pass.
- [ ] No host credentials or signer material in guest.
- [ ] Guest crash/timeout/force-termination cleanup verified.
- [ ] Cross-VM separation and resource caps verified.
- [ ] External security review or penetration test findings triaged.
- [ ] Receipt says exactly which runtime and checks were used.

### Before hosted multi-tenant launch
- [ ] Independent architecture/security review.
- [ ] Production RLS role verified in deployment.
- [ ] Key management and rotation runbook operational.
- [ ] Backups, restore, and disaster recovery tested.
- [ ] Abuse limits and incident response operational.
- [ ] Data retention/deletion controls tested.
- [ ] Per-tenant audit and export tested.
- [ ] Privacy review for every external processor.
- [ ] External penetration test completed and critical/high findings closed.

---

## 9. External standards and references

- OWASP LLM Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP ASVS 5.0: https://asvs.owasp.org/
- NIST SP 800-218 SSDF: https://csrc.nist.gov/pubs/sp/800/218/final
- Firecracker production host setup: https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md
- Firecracker design: https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md
- PostgreSQL Row Security: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- GitHub webhook validation: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- GitHub webhook best practices: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- MCP authorization security (future connector): https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations

---

## 10. Operational rule

The security posture is an executable property, not marketing copy. Every protection listed above must have an owner, a code location, an acceptance test, and a release gate. A control that is only described in a document is not an implemented control.
