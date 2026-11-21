# MicroVM Execution Slice

The microVM execution slice is one Firecracker guest, one fixed safe
workload, host-side evidence, and verified termination — no AI agents,
no model calls, no egress. It is the first vertical of the Gate B
execution plane (ADR-0022) and the foundation every later queue item
(ToolGateway, evidence signing, isolation audits) builds on.

## What the slice is

```
assignment ──► SandboxManager.provision_sandbox
                  │ 1. signature → eligibility → network verdict
                  │ 2. scratch disk + Firecracker boot (under jailer)
                  │ 3. DeliverRunCapability  ──frame──►  guest
                  │ 4. await GUEST_READY (identity verified)
                  ▼
             run_slice workload phase
                  │ guest runs the fixed workload (workload.py)
                  │ guest submits EVIDENCE_MANIFEST_SUBMITTED
                  │ host re-derives the manifest digest → QA status
                  ▼
             request_graceful_shutdown ──frame──► guest
                  │ wait to deadline → force_terminate if still alive
                  ▼
             destroy_sandbox
                  │ stop VMM → close transport → remove scratch
                  │ → remove per-sandbox nftables table → verify (8 probes)
                  ▼
             SliceReport (always written)
```

Three status axes, never collapsed:

| Axis | Values | Meaning |
|---|---|---|
| `execution_status` | `completed`, `provision_failed`, `guest_failed`, `timed_out`, `protocol_violation` | Did the protocol loop finish? |
| `qa_status` | `pass`, `fail`, `not_run` | Did the fixed workload's checks pass? Derived host-side from the digest-verified manifest's `workload_result`. |
| `trust_status` | `verified_clean`, `verification_failed`, `cleanup_incomplete`, `unknown` | Does independent teardown verification hold? |

A slice can be `execution=completed, qa=pass, trust=verification_failed`
— the teardown found residue. Every axis is reported honestly; a failure
on one never masks another.

## Components

| Module | Runs | Responsibility |
|---|---|---|
| `manager.py` | host | Fail-closed provisioning, capability delivery, shutdown request, destroy + 8 teardown probes |
| `slice.py` | host | Orchestration: channel lifecycle, workload phase, termination choice, `SliceReport` |
| `vsock_channel.py` | host | AF_UNIX half of Firecracker's vsock bridge; guest-initiated listener at `<uds>_<PORT>` (port 4242, outside the reserved `[2^30, 2^31)` range) |
| `firecracker_client.py` | host | Real jailer subprocess: chroot staging (hardlinks), serial capture, SIGTERM→grace→SIGKILL, jail cleanup |
| `network.py` | host | `apply_nftables` / `remove_nftables` — per-sandbox `inet workflo_<id>` table, fail-closed |
| `guest_runtime.py` | guest | Capability gate → identity verify → GUEST_READY → fixed workload → manifest → await shutdown |
| `workload.py` | guest | The fixed safe workload: workspace marker, hash determinism vs pinned digest, `/proc/meminfo` sanity |
| `guest_supervisor.py` | guest | Protocol state machine, evidence manifests (metadata-only), failure reporting |

## Capability flow (the trust root for one attempt)

1. Host builds `GuestCapabilityV1` bound to `attempt_id` + `sandbox_id`,
   TTL = the assignment's wall clock, and sends it as the first
   host→guest frame (`RUN_CAPABILITY_DELIVERED`) with its canonical
   digest in the envelope.
2. The guest re-derives the digest from the received payload — a
   mismatch refuses before anything runs.
3. The guest cross-checks the capability against the **boot args**
   (`workflo.attempt_id=… workflo.sandbox_id=…` appended to
   `kernel_boot_args`): a capability that doesn't match the identity the
   host booted the VM with is refused (`GuestIdentityError`).
4. Only then does the supervisor announce `GUEST_READY`. The host
   verifies readiness on the same strictly-ordered session before the
   workload phase begins.

No capability, no ready. No ready, no workload. No verified manifest,
no QA verdict.

## Evidence

- **Serial log** — Firecracker's stdout+stderr (guest console + VMM
  logs) captured per sandbox; sha256 recorded in the lifecycle record.
- **Capability delivery** — id, digest, expiry appended to host evidence
  at delivery time.
- **Manifest** — the guest's `EVIDENCE_MANIFEST_SUBMITTED` payload
  carries the full manifest *and* its digest; the host re-derives the
  digest (`digest_matches`) before reading `workload_result`. A digest
  mismatch is a `protocol_violation`, never a QA answer.
- **Teardown verification** — all 8 `TeardownCheckId`s run by the host
  after destroy: `vmm_exited`, `vm_stopped`, `cgroups_removed`,
  `netns_removed`, `disk_destroyed`, `sockets_closed`,
  `capabilities_expired`, `process_scope_empty`.
- **SliceReport** — JSON written to `output_dir/slice-report-*.json` on
  *every* path, including provision failure (`extra=forbid`).

Guest-supplied facts are labelled as claims; QA derives from the
digest-verified manifest, and trust derives only from host probes.

## Teardown (verified termination)

`destroy_sandbox` order:

1. `client.stop` — SIGTERM → grace → SIGKILL to the VMM process group;
   serial log flushed; jail directory (staged hardlinks, config, sockets)
   removed only after the process is dead.
2. Close the guest transport — the host-side listen socket file is
   sandbox-scoped state and must be gone before verification.
3. Remove the scratch disk.
4. Remove the per-sandbox nftables table (`remove_nftables`) — the table
   that gated the run must go with the run. Applied-but-unremovable
   network state fails the `netns_removed` probe (fail closed).
5. Run all 8 probes independently → `TeardownVerificationV1` with one of
   four outcomes. Probes that cannot run report `unperformable` — never
   a silent pass.

## Running on a KVM host

```bash
# 1. Provision the pinned toolchain (digest-verified):
sudo ./scripts/linux/provision_firecracker.sh
#    (or offline: --from-archive firecracker-v1.18.0-x86_64.tgz)

# 2. Provide pinned guest images (kernel + rootfs containing python3 +
#    workflo_worker_host so init can run the guest runtime):
export WORKFLO_SLICE_KERNEL=/srv/images/vmlinux.bin
export WORKFLO_SLICE_ROOTFS=/srv/images/rootfs.ext4
export WORKFLO_SLICE_ROOTFS_READY=1   # after you've confirmed step 2

# 3. Run the KVM-gated e2e (root + nft required):
sudo pytest worker/tests/integration/test_kvm_boot.py -v
```

On any host missing `/dev/kvm`, `nft`, root, or the pinned artifacts the
tests **skip with an explicit reason**. A skip is a documented
non-proof, never a pass (ADR-0022: mocks do not satisfy Gate B).

Without KVM the slice is still fully tested: the flagship integration
test (`test_slice.py`) runs the real protocol loop, real channel, and
real guest runtime over AF_UNIX with a fake VMM — everything except the
actual boot.

## Known limitations (honest list)

- **Guest images are external.** The slice does not build a rootfs; the
  KVM e2e requires one that contains the guest runtime as its init
  entrypoint. Until provisioned, that test skips.
- **No artifact upload.** The manifest carries digests only; the
  `ARTIFACT_UPLOAD_REQUESTED` message type exists in the registry but
  the slice does not exercise it (no artifact store yet).
- **Cancellation not end-to-end.** `RUN_CANCELLATION_RECEIVED` is
  honoured and recorded by the guest runtime (tested), but the slice
  runner has no cancel trigger yet — that arrives with the
  cancellation-observer queue item.
- **Cgroup enforcement is probe-only.** The `cgroups_removed` teardown
  probe verifies absence; creating per-sandbox cgroups at provision time
  (via jailer `--cgroup` flags) is not wired yet.
- **Serial console parsing is out of scope.** The serial log is captured
  and digested as evidence; nothing parses it for verdicts.
