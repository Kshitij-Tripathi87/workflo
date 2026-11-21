# Phase B — Real MicroVM Worker and Gate B Implementation Plan

**Status:** Prepared; implementation is gated on Phase A contract acceptance  
**Parent:** Agentic Execution Phase plan, AG-010 through AG-016  
**Target boundary:** Linux + KVM + pinned Firecracker/jailer  
**Release rule:** No production agent execution until Gate B passes with real KVM and pinned release artifacts.

## 1. Objective

Replace the current fake-only Firecracker client seam with a production host adapter, connect the existing versioned guest protocol to a real vsock transport, and prove the full lifecycle of one fresh microVM per run attempt.

Phase B is infrastructure work. It does not add new agent behavior, arbitrary shell access, autonomous code modification, Git writes, or production model inference. It proves that the existing trusted worker can safely start, communicate with, monitor, and destroy a real guest.

The existing Docker, bubblewrap, and namespace runtimes remain development/CI-only. If KVM, Firecracker, jailer, pinned guest artifacts, vsock, network enforcement, or teardown verification are unavailable, production admission must reject the worker. No fallback is permitted.

## 2. Phase B deliverable

One reproducible Gate B run must:

1. Verify a signed, attempt-bound assignment and pinned runtime/image digests.
2. Reserve CPU, memory, disk, process and concurrency capacity atomically.
3. Apply default-deny per-VM network isolation before the VM starts.
4. Create a fresh bounded scratch disk and unique vsock endpoint.
5. Launch the pinned Firecracker binary only through the pinned jailer.
6. Boot the pinned guest kernel/rootfs on real KVM.
7. Complete a mutually bound guest-ready handshake over the real vsock channel.
8. Run a harmless, fixed fixture inside the guest; prove forbidden host resources and network destinations are unreachable.
9. Exercise timeout, cancellation, guest crash and host crash/recovery behavior.
10. Terminate the VM and independently prove removal of every process, cgroup, network, socket, disk and temporary credential.
11. Preserve a portable, digest-verified evidence bundle outside the guest.

A mocked client, fake binary, unit test, bwrap run, namespace golden run, or skipped KVM test is not Gate B evidence.

## 3. Existing seams and required changes

| Existing path | Current role | Phase B change |
|---|---|---|
| `worker/src/workflo_worker_host/manager.py` | Typed manager; fake-injected `FirecrackerClient` | Wire production client; pass generated jailer argv; own partial-start rollback |
| `worker/src/workflo_worker_host/admission.py` | KVM/tool/image/capacity eligibility | Require exact pinned binary, jailer, kernel and rootfs digests; fail closed on incomplete probes |
| `worker/src/workflo_worker_host/assignment.py` | Signed V1 + agentic V2 assignment | Consume V2 only for agentic attempts after Phase A; preserve V1 compatibility |
| `worker/src/workflo_worker_host/network.py` | Pure nftables ruleset and injected applier | Add real transactional apply/remove adapter and per-sandbox namespace/tap lifecycle |
| `worker/src/workflo_worker_host/protocol.py` | Versioned, framed, sequenced message validation | Retain as transport-independent validator; add real AF_VSOCK adapter |
| `worker/src/workflo_worker_host/guest_supervisor.py` | Guest identity/readiness/heartbeat/cancel model | Connect to guest init and real transport; reject project work before authenticated readiness |
| `worker/tests/integration/test_kvm_boot.py` | Honest KVM probe; skips without KVM/artifacts | Replace probe-only coverage with required real boot/isolation/teardown suite on protected KVM runner |

Do not duplicate the existing manager, assignment, protocol, evidence, or durable dispatch implementations. Extend their interfaces and retain one source of authority.

## 4. Work package order

### AG-010 — Production Firecracker client

**New module:** `worker/src/workflo_worker_host/firecracker_client.py`

Implement the existing `FirecrackerClient` protocol behind a concrete Linux-only adapter.

Requirements:
- Invoke the pinned jailer using an argument vector; never use `shell=True` or interpolate untrusted strings into a shell command.
- Validate all configured executable, chroot, config, kernel, rootfs, scratch and socket paths against worker-owned roots before launch.
- Write VM configuration atomically with restrictive permissions; reject symlink traversal and pre-existing sandbox paths.
- Launch under a dedicated UID/GID, jailer chroot, cgroup, seccomp and configured resource ceilings.
- Track process identity using PID plus process start-time identity (and pidfd where supported); never trust a recycled PID.
- Bound boot, API readiness, graceful shutdown and forced termination by explicit deadlines.
- Classify spawn failure, jailer rejection, VMM exit, API timeout, guest boot timeout and forced kill as distinct infrastructure outcomes.
- Make `stop` idempotent. An unknown process identity must not be signalled.
- Expose host-observed process/cgroup identity to teardown probes without exposing host control to the guest.
- Ensure a partial start cleans up any created process, socket, disk, cgroup and network state.

**Tests:** fake executable process tests for argv, no-shell behavior, config permissions, path traversal, PID reuse, timeout, signal escalation, repeated stop, process crash, and partial-start rollback.

### AG-011 — Real vsock transport

**New module:** `worker/src/workflo_worker_host/vsock_transport.py`

Connect the existing protocol validator to Linux AF_VSOCK and the Firecracker host-side vsock endpoint.

Requirements:
- Use a bounded, length-prefixed stream with the existing `MAX_MESSAGE_BYTES` and `MAX_PAYLOAD_BYTES` limits.
- Bind every connection to one run, attempt, sandbox, guest CID, protocol version and one-time nonce.
- Complete challenge/response before accepting `GUEST_READY`; validate the signed assignment digest and guest image/runtime identity.
- Enforce strict sequence progression, payload digests, schema validation, read/write deadlines, and bounded reconnect behavior.
- Reject replay, cross-attempt messages, unknown message types, oversized frames, malformed UTF-8/JSON, stale nonces and identity mismatch.
- Handle disconnect as loss of guest liveness; do not silently reconnect into a new or ambiguous guest.
- Keep host operations out of the protocol. Guest messages may request only enumerated lifecycle operations such as readiness, heartbeat, evidence-manifest submission and shutdown acknowledgement.

**Tests:** socketpair/fake transport tests for framing and fault injection; real AF_VSOCK handshake tests on the protected KVM runner.

### AG-012 — Reproducible guest image pipeline

**New/updated location:** `infra/guest-images/` and the existing image build scripts.

Produce versioned, immutable artifacts:
- kernel image;
- minimal root filesystem;
- guest init/supervisor;
- protocol client;
- approved Workflo runtime dependencies;
- optional workload-specific additions only through separately digest-pinned image variants.

Requirements:
- Reproducible build inputs, pinned package versions, SBOM, provenance and SHA-256 manifest.
- No SSH daemon, package manager at runtime, Docker daemon, cloud-init credentials, host mounts or unused services.
- Read-only rootfs; a fresh, size-bounded writable scratch device per attempt.
- Non-root guest supervisor/agent identity after minimal init setup.
- No model weights in the base image unless the manifest explicitly pins the model image variant; Phase B's harmless fixture must not require model inference.
- Sign release manifests outside the guest. Worker admission checks signature, provenance, compatibility and digests before provisioning.

**Tests:** deterministic manifest validation, tamper rejection, image allowlist and compatibility checks. Rebuild comparison must explain any non-reproducible artifact.

### AG-013 — Resource and network lifecycle

**New modules:** `worker/src/workflo_worker_host/resources.py` and `worker/src/workflo_worker_host/network_backend.py`.

Requirements:
- Atomically reserve vCPU, memory, disk, process count and concurrent VM slots before creating resources.
- Reservations are keyed by sandbox/attempt and are idempotently acquired/released.
- A reservation is released only after successful teardown verification; uncertain cleanup quarantines capacity.
- Create isolated tap/network namespace per VM; apply default-deny nftables before VMM launch.
- Block host, loopback escape, private, link-local, metadata, multicast and other reserved destinations regardless of allowlist.
- No DNS-only policy. Resolve and pin allowed destinations before assignment; apply IP/port/protocol rules.
- Roll back network state and reservations on any provisioning failure.
- Enforce cgroup CPU, memory, pids, I/O and wall-clock ceilings; report actual resource observations.
- No shared writable scratch disks or network namespaces between attempts.

**Tests:** concurrent reservation races, quota exhaustion, double release, orphan reservation recovery, network apply failure, partial namespace/tap creation, blocked egress and cleanup.

### AG-014 — Durable worker claim integration

Extend the existing control-plane outbox and worker lease path; do not add a second queue.

Requirements:
- Worker identity is authenticated and revocable.
- A worker claims a lease using an idempotent claim operation; the signed assignment is scoped to tenant/project/run/attempt/sandbox and expires.
- Worker admission happens before accepting the attempt.
- Lease expiry, worker disconnect and heartbeat loss have deterministic state transitions.
- Retry creates a new attempt and new sandbox; never resume an uncertain guest.
- Cancellation is durable and host-enforced. Guest acknowledgement is evidence, not proof of teardown.
- Current in-process/Docker executor is explicitly marked development-only and cannot be selected for production admission.

**Tests:** duplicate outbox delivery, lease race, expired assignment, revoked worker, stale heartbeat, cancellation during each lifecycle stage, worker restart and retry with new sandbox identity.

### AG-015 — Independent teardown verification

Implement host-side probes for:
- Firecracker and jailer process exit, with process identity checked;
- jailer cgroup empty and removed;
- tap device and network namespace removed;
- nftables table/rules removed;
- vsock UDS endpoint removed and no connected peer remains;
- scratch disk securely removed or cryptographically destroyed according to storage policy;
- guest process scope empty;
- temporary capability material and per-attempt credentials revoked/removed;
- resource reservation released only after all required probes pass.

A missing, throwing, inconclusive or unperformable probe is a failed trust check. Do not convert `UNKNOWN` to `PASS`. A failed teardown quarantines the worker and prevents a successful trust receipt.

### AG-016 — Gate B adversarial suite

**Protected runner:** dedicated Linux host with hardware virtualization and `/dev/kvm`, pinned Firecracker/jailer, signed kernel/rootfs artifacts, root privileges and isolated network.

Mandatory scenarios:
1. Happy path: signed assignment → real boot → authenticated guest-ready → harmless fixture → evidence → verified teardown.
2. Assignment tamper, wrong tenant/project, wrong attempt, expired signature, revoked profile and digest mismatch.
3. Missing KVM, wrong Firecracker/jailer binary, wrong image digest, insufficient capacity and unhealthy host.
4. Guest attempts to read host files, host process metadata, host sockets, credentials, container socket and another sandbox's files.
5. Guest attempts metadata/private/link-local/loopback/unauthorized egress and DNS rebinding.
6. Two concurrent VMs prove process, disk, CID, socket, network and workspace separation.
7. CPU, memory, disk, PID, output, log and wall-clock exhaustion.
8. Malformed, oversized, replayed, reordered and cross-attempt vsock messages.
9. Host/guest crash during provision, handshake, execution, upload and teardown.
10. Gateway disconnect, heartbeat timeout, cancellation race and force-kill deadline.
11. Teardown probe failure, orphan detection, worker quarantine and safe recovery.
12. Portable evidence round-trip after artifact download/extraction; independent digest and receipt verification.
13. Negative controls prove that every forbidden access attempt is denied and every tampered artifact/receipt is rejected.

No KVM skip is accepted on the protected Gate B workflow. The workflow must fail if the runner does not expose required capabilities or pinned artifacts. Developer machines without KVM may run unit tests but must report Gate B as NOT RUN.

## 5. Manager lifecycle contract

The host manager should expose one explicit state machine:

`NEW → ADMITTED → RESERVED → NETWORK_READY → VMM_STARTED → GUEST_AUTHENTICATED → RUNNING → STOPPING → TERMINATED`

Any failure transitions to a terminal infrastructure state plus a cleanup obligation. The manager must not expose a READY/RUNNING state before the authenticated guest handshake. Teardown is a separate state result:

- `verified`: every required host probe passed;
- `failed`: one or more probes failed;
- `unknown`: forbidden as a successful terminal trust result; treated as failure for admission/receipt purposes.

Provisioning must use the existing generated jailer argv. The current manager path must not pass an empty argv to the client. The concrete client owns only VMM process lifecycle; the manager owns assignment validation, policy ordering, resource/network orchestration, guest protocol and evidence state.

## 6. Observability and evidence

Record structured, redacted host events for:
- assignment verification and policy/profile/image digests;
- host eligibility and capacity reservation;
- network namespace/tap/ruleset identity;
- jailer/VMM start, process identity, boot readiness and guest identity;
- vsock session identity, sequence number, message type and protocol errors;
- resource peaks and limit events;
- cancellation, shutdown deadline, forced kill;
- teardown probes and final trust status.

Do not record source contents, model prompts, credentials, private keys or raw environment variables. Evidence must be attempt-scoped and digest-addressed. The guest can submit claims; only host-side observations and independent verifiers can establish trusted lifecycle facts.

## 7. Gate B acceptance criteria

Gate B is **PASS** only when all conditions are true on the protected real Linux/KVM runner:

- [ ] Pinned Firecracker and jailer binaries verified by digest and version.
- [ ] Signed, digest-pinned kernel and rootfs verified before boot.
- [ ] Real microVM boots; guest-ready handshake authenticated and bound to exact attempt.
- [ ] Harmless fixture runs only inside guest; no project code executes on host.
- [ ] Host filesystem/process/socket/credential and cross-VM access attempts are denied.
- [ ] Default-deny egress and all forbidden destination tests pass.
- [ ] CPU, memory, disk, process and time limits are enforced.
- [ ] Failure injection at provision, boot, run, transport, upload and teardown is handled safely.
- [ ] Every required teardown probe passes; no resource reservation or orphan remains.
- [ ] Portable evidence bundle survives download/extraction and independent verification.
- [ ] No required test was skipped, mocked, or replaced by a namespace/bwrap run.
- [ ] Exact source commit, assignment, policy, image, binary, test and evidence digests are retained.

Until every item passes, Gate B status remains BLOCKED and production admission rejects the worker.

## 8. Delivery and review sequence

Use one PR per coherent work package, in this order:

1. AG-010 production Firecracker client and manager integration.
2. AG-011 real vsock transport and guest handshake.
3. AG-012 reproducible guest image pipeline.
4. AG-013 resource/network lifecycle and rollback.
5. AG-014 durable worker claim integration.
6. AG-015 independent teardown probes.
7. AG-016 protected KVM adversarial suite and Gate B evidence.

AG-010 and AG-011 may be developed in parallel only after Phase A contracts are accepted; their integration PR must remain sequenced. AG-012 may be built in parallel but cannot be admitted until its manifests are signed and pinned. AG-013 and AG-015 are required before the real Gate B suite. AG-014 must not enable production dispatch before Gate B passes.

Every PR must include:
- a focused design note and threat-boundary impact;
- unit tests plus adversarial failure tests for its module;
- no-shell / fail-closed review;
- compatibility tests for V1 assignment and protocol contracts;
- CI, architecture review and code-owner review;
- exact test evidence and limitations.

## 9. Explicit non-goals for Phase B

- No agent DAG scheduler or parallel specialist execution.
- No arbitrary shell or generic host RPC.
- No customer-uploaded agent bundle or arbitrary guest container.
- No production model-serving acceptance (handled by the model gate).
- No autonomous patching, Git push, PR creation, merge or deployment.
- No use of Docker, bwrap or WSL as a production microVM fallback.
- No claim that a unit/fake test proves hypervisor isolation.

**Phase B is complete only when Gate B has real, reproducible, independently verifiable KVM evidence.**
