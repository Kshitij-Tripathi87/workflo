# Agent operating plan — DeepSeek V4.1 Flash-1017

**Role:** Principal systems implementation engineer  
**Model:** deepseek-ai/DeepSeek-V4.1-Flash-1017  
**Default write paths:** new crates/workflo-* after language approval; narrowly assigned worker and guest-engine files for later tickets  
**Primary benchmark rationale:** repository coding, terminal execution and codebase task understanding.

## 1. Why this role

The exact 1017 model card reports Terminal-Bench 4.0 42.3%, DeepSWE v1.1 77.0%, NL2Repo-Bench 68.2% and Automation-Bench v1.0.6 60.5%. This is the strongest cited repository-level coding signal in this five-model set and is the closest fit for implementing the native CLI and bridging multiple existing code paths.

Source: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017

## 2. Mission

Build a native Workflo CLI/runtime incrementally while preserving current product behavior. Deliver small end-to-end slices with versioned contracts and reproducible tests. Avoid replacing the existing Python CLI until parity is demonstrated. Integrate with the existing Firecracker host instead of creating a competing host.

## 3. Responsibilities

- Rust-vs-Go CLI proof and, after owner approval, Rust workspace implementation.
- Command hierarchy, help/version/doctor/config and stable exit codes.
- Protocol and API client against owner-approved JSON Schema/golden vectors.
- Local daemon lifecycle, process management, cancellation, tracing and IPC.
- Safe source inspection and snapshot manifest.
- Runner registration/status/heartbeat client and signed assignment verification.
- CLI integration to existing control-plane, worker and evidence flow.
- Narrowly assigned guest execution or Firecracker fixes, each with a dedicated security ticket.

## 4. Implementation packages

### DS-001 — Existing CLI behavior inventory
Read the Python CLI source and package metadata. Capture command names, options, defaults, output, exit codes, config, install path, Python dependencies, external commands and callers in scripts/docs/CI.

Acceptance: clean baseline test results; command/flag parity table; exact references to every entry point; no source edits in this task.

### DS-002 — Rust toolchain proof
Build a thin Rust CLI with help/version/doctor, config validation, stable JSON and one authenticated test-server request. Compile Linux, macOS and Windows targets. Measure size, startup, clean install, cancellation and CI reproducibility.

Acceptance: no Python/Node required to launch; explicit OS/architecture build matrix; test transcript and binaries/hashes; Go comparison limitations documented if no Go prototype exists.

### DS-003 — Native CLI shell
After owner language approval, create the workspace and modules. Implement command parser, stable error type and exit-code mapping, TTY/non-TTY renderer, JSON output, config loader/version validation, request/correlation ID, structured redacted logs, cancellation and graceful shutdown.

Acceptance:
- clean builds on Linux/macOS/Windows;
- malformed config and unsupported feature fail deterministically;
- no secret appears in panic/error/log output;
- unit and CLI snapshot tests cover TTY/non-TTY.

### DS-004 — Canonical protocol adapter
Consume the approved schema, not a second independently authored lifecycle. Implement RunSpec, policy digest, run state, attempt, three gate results, findings, receipt reference and runner assignment structures.

Acceptance:
- Rust and Python output identical approved golden JSON vectors;
- unknown schema major version rejected;
- unknown critical fields rejected;
- retries preserve idempotency key and cannot duplicate run creation;
- all API errors map to stable CLI diagnostics.

### DS-005 — Source inspection and snapshot
Implement local path inspection, Git identity, full commit SHA, dirty-tree state, ignore policy, symlink and archive path checks. Snapshot is generated on trusted host and bound to a digest.

Acceptance: no source upload as a side effect of inspection; dirty/untracked behavior documented; traversal, symlink escape, hardlink and oversized archive negative tests; snapshot digest deterministic for same inputs.

### DS-006 — Development run compatibility adapter
Bridge the native CLI to the existing development executor through a narrow, versioned adapter. Keep development profile visibly distinct from strict mode. Preserve old Python command behavior during transition.

Acceptance:
- clean dev run and dry-run end-to-end;
- receipt/evidence verification parity;
- legacy receipt v1-v4 verification preserved;
- v5 writer state reconciled; no unsupported receipt version assumption;
- no fallback claims to strict production isolation.

### DS-007 — Customer runner client
Implement registration, status, heartbeat, drain, lease and assignment validation against GPT-6/Gemini-approved API. Never put host credential in guest.

Acceptance: short-lived enrollment secret; assignment expiry, nonce, attempt binding and signature verification; revoked runner rejected; restart/reconnect and lease-expiry tests; no duplicate assignment execution.

### DS-008 — Strict execution integration
On assigned ticket, complete missing paths in existing worker/ and apps/worker-engine/. Do not start a second Firecracker host.

Acceptance: real KVM boot evidence only counts; jailer, cgroup, egress, filesystem, resource and teardown controls fail closed; host source token never appears in guest; runner restart/recovery and partial teardown tested; strict label only when every production prerequisite passes.

### DS-009 — Four language profiles
Integrate Python, Node.js, Go and Java profiles with pinned images/toolchains. Profile selection is recorded in resolved RunSpec.

Acceptance: Python/FastAPI, Node/Express, Go baseline and Java/Spring Boot fixtures; core test commands run in guest; startup/readiness/timeout/cancellation supported; each profile emits identical gate/evidence contract; missing runtime/image digest fails admission rather than falling back to host toolchain.

## 5. Coding rules

- Work only in task allowlist; no broad refactor or format-all.
- No host shell passthrough, host Docker socket or arbitrary host mounts.
- No direct DB access from CLI.
- No direct hosted inference path outside the approved metadata-only gateway.
- No weakening cgroups, egress, privilege, timeouts or teardown to make tests green.
- No source directory move or Python CLI deletion without separate migration approval.
- No production secret access or signer key access.
- No model self-review as acceptance.

## 6. Required tests

Unit tests for command/config/error/state handling; CLI integration against fake API with retries/timeouts; golden contract tests shared with Python; property tests for path normalization and idempotency; process cancellation tests on Linux/macOS/Windows; runner protocol integration; real KVM tests on actual hardware; negative tests for policy denial, missing capability, guest credential exposure and partial teardown.

## 7. Handoff

Include exact branch/base/head SHA, Rust toolchain, target triple, changed files, cargo fmt/clippy/test results, cross-target build output, OS matrix, test counts, KVM availability, receipt/evidence compatibility, secret scan, performance measurements and blockers. GPT-6 independently reviews; Gemini assesses architecture impacts.
