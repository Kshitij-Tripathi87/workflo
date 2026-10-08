# P4 — Real Execution Acceptance

> Status: **specification**. Nothing in this document is claimed as passing
> unless its row says PROVEN and names the command that was run.
>
> Baseline: `a2cc6cb` (stabilization). P0–P3 established *repo* integrity:
> clean builds, reproducible installs, real type checking, fail-closed
> production config, isolated tests, documented boundaries. P4 is the first
> gate that tests the **product claim** — that Workflo runs untrusted code in a
> sealed sandbox and returns an independently verifiable receipt.

## Why this gate exists

Every artifact so far is a proxy. A green `ruff` run, a frozen lockfile, a
passing `next build` — none of them demonstrate that

```
untrusted repository ──► sealed sandbox ──► governed exploration ──►
confirmed finding ──► signed receipt ──► independent verification ──► VALID
```

is true. The website redesign stays frozen until this chain is demonstrated
end-to-end, because UI work on an unproven core is decoration.

## The acceptance chain

Each link names the component that must be exercised and how it is observed.
"Evidence" is the artifact a reviewer reads — not a log line.

| # | Link | Component | Status | Evidence required |
| --- | --- | --- | --- | --- |
| 1 | GitHub URL → ref resolved to immutable SHA | `scripts/linux/*`, supervisor | REQUIRES-CI | Resolved SHA recorded in the receipt; `--ref` that moves mid-run cannot change it |
| 2 | Pinned clone | supervisor | REQUIRES-CI | Clone dir contains the declared SHA; no network after clone |
| 3 | Sealed Linux sandbox | bwrap + cgroups v2 + netns + seccomp + Landlock | REQUIRES-CI | `isolation_created{cgroup,netns,landlock_abi}` in the ledger; Landlock status files APPLIED |
| 4 | Network policy actually blocks egress | `sandbox_runtime.network` | REQUIRES-CI | Probe asserts DNS/egress denial from *inside* the sandbox |
| 5 | Application boots under isolation | worker / golden run | REQUIRES-CI | App HTTP 200 observed from inside the namespace |
| 6 | Real model inference | vLLM (`infra/vllm`) or the inference gateway | REQUIRES-GPU | Non-stub completion with token usage; see `bench/model-serving` |
| 7 | Explorer drives the run | agent layer | REQUIRES-CI | `AgentActivity` events with tool calls and goals |
| 8 | ToolGateway authorizes every call | `ToolGateway` | LOCAL-PROVEN | Denied calls recorded; see negative path N1 |
| 9 | Observation ledger is complete + tamper-evident | `evidence.py` | LOCAL-PROVEN | `verify_evidence_bundle` passes; deleting/altering an event fails it |
| 10 | Judge confirms or rejects candidates | judge | REQUIRES-CI | A false candidate is rejected (N3) |
| 11 | Teardown verified | supervisor teardown | REQUIRES-CI | Teardown proof: cgroup empty, netns gone, no residue (N6) |
| 12 | Ed25519 receipt signed | `app/core/receipts.py`, `verify_receipt_signature` | LOCAL-PROVEN | Signature verifies with the run's public key |
| 13 | Transparency proof (Merkle) | `apps/control-plane` transparency log | LOCAL-PROVEN | Inclusion proof verifies; tampering breaks it (N5) |
| 14 | Independent verifier returns VALID | verifier CLI | LOCAL-PROVEN | `VALID` for an honest bundle, `INVALID` for tampered ones (N4) |

Status legend — **LOCAL-PROVEN**: demonstrable on a developer machine with the
dependencies installed, and demonstrated. **REQUIRES-CI**: needs the
root/kernel/bwrap environment (`linux-gate.yml`). **REQUIRES-GPU**: needs a real
model endpoint. **NOT PROVEN**: no evidence exists yet.

## Negative paths (the ones that matter)

A system that only demonstrates the happy path has not been tested. Each of
these must produce the stated failure, and each is a test, not a manual check.

| # | Scenario | Required outcome | Status |
| --- | --- | --- | --- |
| N1 | Agent requests an unauthorized tool | **DENY**, recorded in the ledger | LOCAL-PROVEN (`test_agent_gate.py`, `ToolGateway` tests) |
| N2 | Sandbox tries to reach the network | **DENY** (DNS + egress probes fail) | REQUIRES-CI (`test_network_gate.py`) |
| N3 | Candidate finding is fabricated / not reproducible | **NOT CONFIRMED** by the judge | REQUIRES-CI |
| N4 | Receipt bytes altered after signing | **INVALID** | LOCAL-PROVEN (`test_verifiable_receipts.py`) |
| N5 | Transparency inclusion proof forged or log entry removed | **INVALID** | LOCAL-PROVEN (`test_transparency*.py`) |
| N6 | Sandbox leaves residue (process, cgroup, netns, mount) | **FAILURE**, teardown proof absent | REQUIRES-CI |
| N7 | Unsafe production configuration | **STARTUP FAILURE**, exit 1 | **PROVEN** (`apps/control-plane/tests/test_startup_guards.py`, 20 tests) |
| N8 | Model endpoint unavailable | **controlled failure**, exit 1, partial report retained | **PROVEN** (`bench/model-serving/bench_inference.py`: connection refused → exit 1, report written; HTTP 500 → counted as failure) |
| N9 | Security gate cannot run (capability missing) | **gate FAILS**, never reports success | **PROVEN** (`linux-gate.yml` assertion steps: 33 skipped → exit 1; verified against fabricated reports) |
| N10 | Benchmark harness absent | **test FAILS** (never skips to green) | **PROVEN** (`test_bench_inference.py` asserts the harness exists) |

## Running the locally-executable subset

```bash
# N4/N5/12/13/14 — receipts, transparency, verification
python -m pytest backend/tests -q                       # 170 tests incl. receipt + writeback
python -m pytest packages/sandbox-runtime/tests -q      # 476 tests incl. evidence bundle
python -m pytest supervisor/tests -q                    # 12 tests incl. IPC lifecycle

# N7 — fail-closed production startup
cd apps/control-plane && PRODUCTION=true python -c "import app.main"   # expect exit 1
python -m pytest apps/control-plane/tests/test_startup_guards.py -q    # 20 tests

# N8/N10 + benchmark economics (stub endpoint, no GPU required by the test)
python -m pytest packages/sandbox-runtime/tests/test_bench_inference.py -q
python bench/model-serving/bench_inference.py \
    --base-url http://localhost:8000 --model Qwen/Qwen2.5-Coder-7B-AWQ \
    --levels 1,2,4 --requests-per-level 32 \
    --gpu-hourly-usd <your real rate> \
    --out bench/results/vllm.json --md bench/results/vllm.md
```

The CI-executable remainder (`linux-gate.yml`) is a single workflow: it
provisions the isolation stack as root, runs the integration gate with a
**no-skips** assertion, then runs the three golden runs (namespaces, agent,
planner) and uploads their receipts.

## Exit criteria for P4

1. Every REQUIRES-CI row has evidence from a real `linux-gate.yml` run on `main`
   — not a local re-run, not a mocked suite.
2. Every negative path row produces its stated failure, each as an automated
   test.
3. One real end-to-end run from a public GitHub URL, with the receipt verified by
   the independent verifier on a machine that did not produce it.
4. The model-serving numbers (`bench/results/*.md`) come from a real endpoint,
   with the hourly cost assumption stated in the report.

## What P4 deliberately does not include

- Website/product-UI work (still frozen).
- New features, connectors, or policy semantics.
- Multi-replica or multi-tenant scaling. Prove one honest run first.

## Honest summary of where this stands

Repo integrity: **green**. Sandbox isolation and golden runs: **implemented,
unproven in CI** (the workflow that proves them could not even be parsed before
`a2cc6cb`). Receipt/verification semantics: **proven locally**. Real model
inference: **not yet run against a real endpoint** — the harness and its
negative paths exist, so the first run needs only a vLLM instance and a cost
number.
