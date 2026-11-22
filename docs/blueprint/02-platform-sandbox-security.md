# 02 — Platform Sandbox and Security Specification

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)  
**Classification:** Security-critical implementation requirements  
**Policy:** No downgrade from strict to development runtime.

## 1. Threat model

### 1.1 Assets to protect

- Developer workstation, host OS and user account.
- Repository source, uncommitted work, credentials, environment variables and private dependencies.
- Other local processes, projects, tenants and concurrent VM runs.
- Customer provider credentials and Workflo runner identity.
- Control-plane signing keys, database and project data.
- Receipt signer, evidence ledger, proof bundle and trusted public keys.
- Network services on local/private networks, cloud metadata endpoints and external endpoints.
- Integrity of agent activity, test results, runtime identity and teardown verification.

### 1.2 Adversary-controlled inputs

Treat all of the following as untrusted, even if the user owns the repository:

1. Repository code and metadata.
2. Dependency packages, install hooks, build scripts, test scripts and compiler plugins.
3. Test output, stdout/stderr, log content, exception text and stack traces.
4. Browser DOM, HTTP responses, API error payloads and downloaded files.
5. Prompt text embedded in repository files, docs, test names, comments or web pages.
6. Agent-generated tool plans and arguments.
7. Provider API responses, model outputs and streamed chunks.
8. Source archive file names, paths, symlinks, submodules and archive metadata.
9. Network names, DNS answers, redirects, proxy environment variables and certificates.
10. Guest protocol frames received from a compromised or malformed guest.

### 1.3 Security assumptions and limits

- The host OS, hypervisor, trusted host adapter, control plane and signing/verifier code form a trusted computing base. Workflo must publish this limitation.
- A VM boundary reduces blast radius; it does not guarantee no hypervisor vulnerability exists.
- A successful check or verified receipt does not prove software is free of defects or vulnerabilities.
- A signed receipt proves the signed bytes were issued by the key and have not changed since signing, subject to key trust and verifier correctness.
- A clean teardown probe is only as strong as the specific resource inventory the host controls and measures.
- Local endpoint addresses such as `127.0.0.1` can be reached by non-user-controlled processes on the same host; the user must understand whether a local model server is trusted.
- Cross-platform VM backends have different host APIs, transport and evidence semantics. A shared API does not make them equivalently secure.

## 2. Security architecture

### 2.1 Trusted host / untrusted guest

The host is responsible for provisioning, restrictions, lifecycle and independent verification. The guest is a disposable computer running repository-controlled workloads. It does not possess authority over the host.

The host/guest protocol is deliberately narrow. The host exposes typed lifecycle operations, not shell commands or arbitrary file access. The guest may send bounded messages, evidence digests and status. All messages are authenticated/bound to the run assignment, sequence number, attempt and capability expiry.

### 2.2 Isolation layers

| Layer | Required control | Enforcement owner |
|---|---|---|
| Hardware virtualization | Per-run VM; hardware-backed VM isolation; supported hypervisor | OS backend / hypervisor |
| VMM process | Pinned binary and digest, jailer or platform equivalent, least privilege | Host adapter |
| Guest kernel | Pinned kernel/rootfs, immutable base, known configuration | Image build + host admission |
| Filesystem | No host bind mounts, separate read-only source, ephemeral scratch, no host credential paths | Host adapter + guest image |
| Process | Unprivileged workload, PID limits, process group/scope, kill escalation | Guest init + host adapter |
| CPU/memory | vCPU cap, memory cap, cgroup/VM limits, wall-clock deadline | Hypervisor + host |
| Disk/I/O | Fixed disk size, quotas, bounded logs/output, no persistent snapshot | Host + guest |
| Network | Egress default deny, allowlisted proxy, DNS/IP control, metadata/private IP block | Host firewall / virtual network |
| Secrets | No host secrets in guest; separate provider gateway; short-lived assignment credential | CLI/vault/control plane |
| Agent | Capability allowlist, typed tool schemas, rate/step/time/output budgets | Agent supervisor + ToolGateway |
| Evidence | Append-only host-controlled ledger, digest chain, independent verifier | Host + evidence service |
| Teardown | Graceful shutdown then force kill; independent resource probes | Host adapter |

## 3. Filesystem policy

### 3.1 Input workspace

- The host creates a new, unique input image or content-addressed snapshot per run attempt.
- Guest source is read-only by default.
- Host source checkout is never mounted directly into the VM.
- No shared folder, clipboard or guest-agent file transfer service is enabled unless the transfer is a bounded, authenticated artifact channel.
- Resolve all paths against the declared workspace root; reject path traversal, absolute paths and unsafe Unicode/normalization collisions.
- Reject symlinks pointing outside the root; preserve in-root symlinks only when policy explicitly allows and verifies the resolved target remains inside root. The conservative initial profile should reject symlinks entirely.
- Reject device nodes, sockets, FIFOs, hardlink surprises and archive entries with traversal components.
- Treat submodules and Git LFS objects as separately pinned artifacts; no implicit credential propagation.
- Ensure file count, total bytes, individual file size, directory depth and path length are bounded.

### 3.2 Writable output

- Use a separate ephemeral writable scratch volume.
- Build outputs, package caches and temporary files live on scratch; they do not mutate original source snapshot.
- If a project requires modifications for build, use a guest-side copy-on-write overlay with a separate diff digest.
- No writable host mount.
- No persistent guest disk reuse between runs.
- Disable or explicitly classify VM snapshots. Production strict profile must not retain restorable guest memory/disk snapshots.
- At termination, destroy ephemeral disk according to platform guarantees; verify the disk resource no longer exists and cannot be reopened. Do not report “secure wipe” if the underlying storage semantics only prove file deletion or ephemeral key discard.

### 3.3 Evidence storage separation

Evidence is written by a trusted host collector to a host-controlled directory or remote evidence service, not to a path writable by the guest. Guest output is accepted over the typed protocol, size/schema validated, then copied into an immutable host-side object and hashed. Never mount the host evidence directory in the guest.

## 4. Process, privilege and resource controls

### 4.1 Guest privilege

- Guest boot/init may use root to establish the sandbox, then drop to a dedicated unprivileged workload user before repository-controlled code runs.
- No sudo, passwordless root, privileged Docker socket, host kernel modules or device passthrough to guest workload.
- Remove package-manager caches and host credentials from the runtime environment.
- Minimal Linux capabilities; drop all not explicitly required.
- Use seccomp and other kernel confinement on guest processes where compatibility permits; log the exact profile digest.

### 4.2 Host process

- Run the hypervisor under jailer or OS equivalent with dedicated UID/GID, restricted filesystem view, seccomp and cgroup/system resource limits.
- VMM binary and jailer are pinned by digest and version; no “latest” mutable downloads on production boot.
- Do not inherit host environment wholesale. Pass a minimal allowlisted environment.
- Spawn with argument arrays (no shell interpolation). Record executable path/digest, argv digest, start time, PID/process scope and exit status; avoid writing secret argv.
- Track all descendants and VMM helper processes with a dedicated process scope.
- On shutdown: cooperative request, bounded grace, force termination, wait/reap, then verify the process scope empty.

### 4.3 Resource envelope

Resource limits are signed in the assignment and enforced by the host, not chosen by the guest:

| Resource | Required limits |
|---|---|
| vCPU | Upper bound per run and per runner |
| Memory | Guest memory cap, host RSS safety reserve, OOM behavior |
| Disk | Rootfs immutable; scratch maximum; inode count and log cap |
| Process count | Maximum guest processes/threads; `fork`/spawn exhaustion test |
| File descriptors | Per-process and VM/service limits |
| Wall-clock | Total run deadline plus phase-specific deadlines |
| CPU time | Optional quota in addition to vCPU count |
| Network | Bytes, concurrent connections, request count and DNS query budget |
| Agent | Maximum reasoning batches, steps, tool calls and per-tool duration |
| Outputs | Max response/body/DOM/log bytes and truncation metadata |

If a limit cannot be enforced or measured, the corresponding assurance claim is marked unavailable and strict admission fails. “Best effort” metrics must not be described as hard limits.

## 5. Network isolation and egress

### 5.1 Default policy

Default guest network = **deny all egress**. The app under test can communicate within its own isolated guest network. The host must not provide general DNS, NAT or internet access by default.

### 5.2 Dependency preparation

Package installation is a major risk because lifecycle hooks and transitive dependencies execute arbitrary code. A single run must not switch the same trusted VM from unrestricted internet install to sealed execution without an explicit trust model.

Recommended design:

1. Resolve/pin dependencies outside the workload VM or inside a separate disposable preparation VM with strict registry allowlist.
2. Produce a dependency bundle/artifact with lockfile, origin, hashes and provenance.
3. Terminate preparation VM and independently verify its teardown.
4. Mount the immutable dependency artifact into the sealed test VM read-only.
5. Run tests with egress denied.

If a user enables live egress during a test, the run must use a separate explicit network policy, display warning, record destinations and downgrade the privacy claim accordingly.

### 5.3 Egress proxy

If network access is required:

- Only host-owned egress proxy is the guest's route.
- Proxy policy is bound into run assignment and receipt.
- Validate DNS answer and destination IP after resolution; protect against DNS rebinding.
- Block loopback, link-local, private, multicast, reserved and cloud metadata addresses unless a specific internal destination is explicitly permitted.
- Prevent redirect-following into disallowed domains/IPs.
- Apply per-run rate, byte and connection caps.
- Do not allow guest-controlled `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, custom DNS or resolver config to bypass the proxy.
- Deny inbound guest network access from host/other runs except the one internal app-testing path.
- Canary test must attempt known external/private/metadata destinations and record blocked results.
- If ruleset enforcement cannot be verified, do not boot a strict VM.

### 5.4 DNS policy

DNS should be controlled by host proxy/resolver. Record queried names and resolved address classes, not full URL query strings or secrets. Deny rebinding and mixed permitted/blocked response sets. A hostname allowlist alone is insufficient; check resolved addresses and redirects.

## 6. Credential isolation

- Provider keys for cloud inference reside in the control-plane secret vault (or customer-owned secret manager), not in guest or local project config.
- Local provider credentials remain on the customer runner and are injected only into the runner-side adapter, never into the guest workload environment.
- Repository checkout tokens are used only by trusted snapshot acquisition and are removed before VM creation.
- No `.env` or developer shell environment inheritance.
- No SSH agent socket, Git credential helper, cloud CLI token cache, browser profile or OS credential-store mount into the VM.
- All secrets use short-lived scopes, one-attempt authorization and explicit expiry.
- Never place raw key bytes into CLI arguments, telemetry, traces, environment dumps, report, receipt or browser localStorage.
- Redaction must happen before logging as well as before export; redacting at report-render time is too late.
- Secret scan is defense-in-depth, not the authorization boundary.

## 7. Agent and tool safety

### 7.1 Prompt injection

Repository docs, package READMEs, webpages, comments, issue text, test output and logs may contain instructions attempting to override agent rules. Treat all such content as data, never policy. System policy is code-owned and provider output cannot modify it.

### 7.2 Tool allowlist

Each tool definition must include:

- immutable tool id/version;
- input/output Pydantic schema;
- declared capability required;
- path/URL scoping rule;
- maximum request/response bytes;
- timeout and concurrency limits;
- evidence record schema;
- redaction rules;
- whether it is enabled for cloud or local model mode.

No generic command execution or `read_file` in cloud mode. All commands are selected from user-declared check definitions and run by the trusted guest supervisor; the model can select among declared check ids, not invent arbitrary argv.

### 7.3 Browser safety

- Browser runs inside guest; no host profile reuse.
- No password autofill, host cookies, browser wallet, password manager or host credential sync.
- Restrict navigation to the app's internal origin and explicitly approved test domains.
- Deny local host addresses and cloud metadata.
- Downloads are quarantined, size-limited and never auto-opened on host.
- Page content is untrusted. Cloud mode does not forward DOM/page text.
- Browser extension installation disabled.
- Playwright/browser binary version and profile image digest are pinned.

### 7.4 Repair suggestions

- Generate patch in an isolated copy or patch artifact generator.
- Never write to original repo by default.
- Record exact paths and patch digest; reject absolute paths, traversal and unsafe symlink targets.
- Test suggested patch in a new run/attempt, not in-place inside current successful evidence run.
- Display “AI-generated suggestion — not independently validated” until re-run validates it.
- The prototype has no `--apply` command.

## 8. Evidence integrity and teardown

### 8.1 Evidence channel

- Guest sends a framed, bounded protocol message over VSOCK/virtio socket/Hyper-V socket adapter.
- Verify frame length, schema version, message type, sequence number, attempt binding, capability and message digest.
- Reject duplicate, out-of-order, oversized, unknown or stale messages.
- Guest never chooses the final receipt status. It submits observations and evidence; host/verifier recomputes admissible outcomes.
- Evidence is appended on host or evidence service, hash-chained, content-addressed and finalized to a manifest.
- Signer uses a distinct host-side key. A guest cannot invoke signer directly or access key bytes.

### 8.2 Trust-source tags

Every record has exactly one primary origin:

- `host_measured`: host-observed process, VM, disk, policy application, network rule, image identity, runtime version, elapsed times.
- `guest_reported`: guest test output digest, guest workload phase, application health, guest-side test counts.
- `agent_observed`: tool result or observed API/browser status, scoped to that tool and result schema.
- `model_generated`: explanation, hypothesis, prioritization or suggested fix.

Do not upgrade an agent/model claim to host-measured. The report should show provenance labels and links to supporting evidence IDs.

### 8.3 Canonical teardown requirements

The current v5 receipt contract requires eight teardown checks:

1. VMM exited.
2. VM stopped.
3. Cgroups removed.
4. Network namespace / network policy resources removed.
5. Scratch disk destroyed.
6. Sockets closed.
7. Capabilities expired or invalidated.
8. Process scope empty.

Each check must be performed independently by the host using platform-specific probes. If a resource was never provisioned, the evidence should state why it is not applicable and the verifier must validate that this is true from the admitted runtime/configuration; a blanket “not present” check cannot prove a configured limit was enforced.

**Important current-code gap:** `worker/src/workflo_worker_host/manager.py` comments explain that the current slice does not create cgroups or a network namespace in the manager and the corresponding checks inspect that managed paths are absent. This does not establish that cgroup CPU/memory/process enforcement or a network firewall was active. The implementation must create those resources and verify their applied configuration, or the assignment must be ineligible for strict execution.

### 8.4 Teardown order

1. Stop admitting new tool calls.
2. Expire/revoke guest capability.
3. Send graceful shutdown with deadline.
4. Wait for guest ack or deadline.
5. Terminate guest VM; kill VMM process group if required.
6. Wait/reap process and verify no child remains.
7. Close VSOCK/virtio/Hyper-V sockets.
8. Remove firewall/egress policy and verify it is gone.
9. Destroy scratch disk/ephemeral storage and verify no live resource remains.
10. Remove cgroup/process scope and verify absence/emptiness.
11. Verify no VM process, listener, mount, tap, veth, namespace or temporary host path remains.
12. Persist teardown verification record.
13. Only then allow receipt finalization.

If any required probe cannot run, it fails closed and yields `UNKNOWN`, `CLEANUP_INCOMPLETE` or `VERIFICATION_FAILED` as defined by the canonical schema. Do not produce a clean trust outcome.

## 9. Platform-specific implementation requirements

### 9.1 Linux / Firecracker

- Use Firecracker + jailer under KVM on supported x86_64/aarch64.
- Pin Firecracker and jailer binary digests and versions.
- Use a dedicated low-privilege UID/GID and restricted chroot/jail.
- Provision a fresh rootfs and scratch disk; rootfs read-only.
- Put VMM and guest workload in host-controlled cgroup hierarchy with CPU/memory/PID/I/O limits.
- Apply seccomp profile and verify installation; use kernel namespace boundaries and network firewall/namespace according to the threat model.
- Use private virtual network per run, no shared tap/bridge across tenants unless rules isolate every tenant.
- Attach vsock listener with socket permissions specific to run; close and verify both host and guest direction sockets.
- Force-kill test the VMM and worker; simulate host process crash and restart recovery.
- Run actual KVM boot on a real self-hosted Linux runner. Mock Firecracker client tests are unit tests, not Gate B evidence.

### 9.2 macOS / Virtualization.framework

- Implement a small Swift helper using Apple's Virtualization.framework; Python host manager communicates over a local framed IPC contract.
- Use a minimal signed helper, sandboxed entitlement set and `com.apple.security.virtualization` entitlement where required by distribution model.
- Create a fresh Linux VM and ephemeral disk per attempt. Never mount host source directory directly into guest.
- Use VM-private virtual network with no external route by default. If egress is needed, route only through host-controlled proxy and prove firewall cannot be bypassed from guest.
- Verify host-side VM process exits, virtual disk is detached/deleted or encryption key discarded as designed, sockets closed and local network interface/rules removed.
- Test Apple Silicon and Intel separately where both are advertised; publish architecture-specific guest artifact support.
- Test signed/notarized installer, entitlement behavior and upgrade/revocation.
- A macOS adapter is not strict until it passes a host-escape, network-bypass, resource-exhaustion and forced-termination matrix on actual hardware.

### 9.3 Windows / Hyper-V

- Implement a small native service/helper using supported Hyper-V APIs and a narrow authenticated IPC contract; do not expose PowerShell/host shell to guest.
- Hyper-V manager creates a fresh Linux VM/disk and isolated virtual switch/network per attempt.
- Explicitly model supported Windows editions. Windows Home must not be assumed to support local Hyper-V; show remote runner alternative.
- Use Hyper-V resource controls (processor/memory/disk) and host process/service isolation; set VM networking to deny egress by default.
- Use Hyper-V Socket/VMBus or a proven transport for typed host/guest protocol; never open arbitrary host listening ports.
- Verify VM state `Off`, VM worker process is gone, disk attachment released/destroyed, switch/firewall resources removed, sockets closed and run capability expired.
- Test host reboot, service crash, VM crash, guest hang, low-memory and disk-full scenarios.
- Sign and verify installer/service binaries; protect service config and runner private key with Windows OS protection.

### 9.4 Remote Linux runner

- Runner is installed by customer on their infrastructure and connects outbound.
- It must support the same signed assignment, policy, evidence and receipt contract as local execution.
- The customer controls source custody, VM host and local model endpoint.
- Remote runner identity and machine measurements are included in receipt; do not claim Workflo has independently audited the customer's physical host.
- Runner registration/revocation, leases, heartbeat and software update are required.

## 10. Strict-mode admission matrix

The backend must report individual checks, not a boolean:

| Capability | `strict` admission condition | If missing |
|---|---|---|
| Hypervisor | Approved version and hardware support | Ineligible |
| Guest artifacts | Signature + exact image digests | Ineligible |
| Host privileges | Least-privilege VMM/jailer/helper configuration | Ineligible |
| CPU/memory/disk/process quotas | Enforced and measurable | Ineligible |
| Network deny | Firewall/proxy policy applied and verified | Ineligible |
| Filesystem boundary | No host shares; read-only input; ephemeral writable disk | Ineligible |
| Host/guest protocol | Version, size, identity, sequence and expiry verified | Ineligible |
| Evidence collector | Trusted path, bounded protocol, signer key protected | Ineligible |
| Teardown probes | All required probes executable | Ineligible |
| Clock/deadline | Monotonic deadline source available | Ineligible |
| Provider privacy | Cloud mode pinned to approved gateway and schema | Cloud agent unavailable; local mode may be allowed |

## 11. Security acceptance test matrix

| ID | Attack / failure | Expected behavior |
|---|---|---|
| SEC-001 | Repository contains `../../` paths in archive | Snapshot rejected before VM start |
| SEC-002 | Symlink points outside checkout | Rejected or safely omitted only by explicit policy; no host read |
| SEC-003 | Package install script attempts host path | Only guest filesystem visible |
| SEC-004 | Test reads `.ssh`, cloud credentials or runner vault | Path unavailable; no secret material |
| SEC-005 | Process fork/thread exhaustion | PID/process limit enforced; VM remains bounded |
| SEC-006 | Memory exhaustion | Memory limit enforced; classified OOM/infra failure |
| SEC-007 | Disk fills scratch volume | Quota enforced; logs bounded; cleanup still performed |
| SEC-008 | CPU busy loop | CPU/wall-clock policy terminates run |
| SEC-009 | Guest tries external DNS / TCP | Denied and recorded |
| SEC-010 | Guest attempts DNS rebinding to private address | Blocked after resolution/redirect validation |
| SEC-011 | Guest tries `169.254.169.254` or equivalent metadata IP | Blocked |
| SEC-012 | Guest tries access host loopback/private LAN | Blocked unless explicit app-internal route, which is guest-only |
| SEC-013 | Prompt injection in README or webpage | No policy/tool privilege change |
| SEC-014 | Model invents `shell` or unknown tool | Strict schema rejects; denial recorded |
| SEC-015 | Model sends traversal path to `read_file` | Denied by local tool path resolver |
| SEC-016 | Cloud payload contains source sentinel in test output | Request rejected locally before egress; capture test sees no sentinel |
| SEC-017 | Cloud provider unavailable | Run pauses/fails model stage; no local/cloud automatic downgrade or data change |
| SEC-018 | Local model endpoint unavailable | No cloud fallback; clear error |
| SEC-019 | Guest sends oversized frame | Host closes protocol session; run fails safely |
| SEC-020 | Guest sends replayed/stale capability | Rejected |
| SEC-021 | Guest alters evidence file after sending digest | Independent host digest mismatch |
| SEC-022 | Guest tries to write receipt or signer key | No access; signer operation remains host-only |
| SEC-023 | VMM ignores graceful shutdown | Host force terminates; process cleanup independently verified |
| SEC-024 | Worker killed while VM running | Recovery controller reaps VM or trust stays unknown; no false clean receipt |
| SEC-025 | Firewall removal fails | Teardown not clean; receipt trust state non-clean |
| SEC-026 | Scratch disk destruction fails | Teardown incomplete; never `verified_clean` |
| SEC-027 | VM survives host runner process restart | Recovery inventory finds VM and terminates/fences it |
| SEC-028 | Receipt bytes changed | Offline verifier rejects |
| SEC-029 | Evidence bundle swapped between runs | Binding mismatch; verifier rejects |
| SEC-030 | Receipt key is unknown/untrusted | Signature may be mathematically valid but trust anchor not established; verifier reports untrusted signer |
| SEC-031 | Two tenants attempt to read same run | PostgreSQL RLS + API auth deny |
| SEC-032 | Windows/macOS adapter not certified | Strict run unavailable; explicit remote runner requirement |

## 12. Security gate model

Each backend gate must produce machine-readable evidence containing:

- host OS build, kernel/hypervisor version and architecture;
- backend and VMM/helper version plus binary digests;
- guest image kernel/rootfs digest;
- signed assignment and policy digest;
- actual enforcement observations for limits/network/filesystem;
- test IDs and outcomes for every mandatory security case;
- failure-injection scenario and recovery outcome;
- teardown checks and independent verifier result;
- exact source commit of Workflo runtime and test harness.

A gate is either `PASS`, `FAIL`, `BLOCKED` or `NOT_RUN`. `NOT_RUN` is never treated as PASS. A capability not implemented is `BLOCKED`, not a skipped test that turns green.

## 13. Security docs to publish

- Threat model and trust boundaries.
- Isolation profile definitions and runtime support matrix.
- Data flow diagram for local/cloud inference.
- Credential handling and retention policy.
- Evidence and receipt verification semantics.
- Known limitations and tested host configurations.
- Vulnerability disclosure and security update policy.
- Release gate evidence per runtime backend.

A Workflo security page must distinguish design goals from tested properties. Only report claims supported by gate evidence for the released build.