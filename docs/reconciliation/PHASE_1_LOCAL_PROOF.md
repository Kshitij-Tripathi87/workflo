# Phase 1: Local integration-change proof (WF-ARCH-004)

The first AI Integration Reliability demo compares two exact revisions of one
fixture repository against the **same** checks and runtime policy. No provider,
model, hosted service, or API key is involved. It runs on a local development
runner, not through the control plane.

## Review the change

The mock provider renames the response field `text` to `output_text`. The exact
consumer is [`response_text()` in `integration.py`](../../examples/integration-migration/source/integration.py).
At the baseline, the incoming response fails the new-contract check while the
old response still passes. The [candidate patch](../../examples/integration-migration/candidate.patch)
changes only that adapter to accept `output_text` and retains the old behavior.
Both revisions run the [same check file](../../examples/integration-migration/source/checks/contract.py).
This is a hand-authored change and a reviewable fixture patch, not an automatic
upstream detector, repair generator, or publisher.

## Run the demo

On a dedicated Linux **development** host with cgroups v2, bubblewrap, seccomp,
and Landlock, provision the CLI and trusted runtime tree, then run:

```sh
sudo bash scripts/linux/setup_env.sh
sudo bash scripts/linux/integration_change_demo.sh /tmp/workflo-integration-change
```

Choose a directory that does not already exist. Setup installs dependencies; the
checks themselves do not fetch dependencies or connect to any network service.
Use `--fixture-only` before the output directory to create the reproducible
repository and print both commits without sandbox tooling or root.

| Revision | QA result | `run-dev` exit | `verify` exit |
| --- | --- | --- | --- |
| Baseline `e42776d206fe11988a3e4b9866b65ae33b3af867` | 1 passed, 1 verified failure (`test_incoming_provider_contract`) | 1 | 0 |
| Candidate `9bd315108a15b2c17dbee1871ac7765110fc33f5` | 2 passed | 0 | 0 |

HEAD is already at the candidate when the baseline runs. Workflo reads tracked
Git blobs at the full SHA, not the index or working tree. The demo does not push
or deploy either revision.

For a different reviewed local project with a self-contained pytest check:

```sh
sudo /opt/workflo/venv/bin/workflo run-dev \
  --repo /path/to/local/repo --commit <full-lowercase-git-sha1> \
  --test-file tests/test_integration.py --output-dir /tmp/my-new-proof
```

The fixed profile admits one tracked pytest file, at most 512 regular files and
16 MiB of materialized source. It excludes common secret paths, rejects symlinks
and submodules, and does not use checkout filters, pytest project configuration,
`conftest.py`, auto-loaded plugins, or dependency installation. Runtime-provided
pytest and its JSON reporter are the only tool dependencies. Use reviewed tests
and a trusted, host-owned runtime tree; this profile is not a service for
arbitrary untrusted repositories. Paths and test IDs are metadata and may still
be sensitive. Check results are required for every collected test; skips,
collection/setup/pytest-teardown errors, empty or missing reports, timeouts, and
runner faults are not treated as product findings.

- **0**: completed checks passed, host teardown verified, receipt issued.
- **1**: completed checks found a failure, host teardown verified, receipt issued.
- **2**: policy rejected the run before launch; no receipt.
- **4**: host teardown or attestation verification failed; no receipt.
- **6**: infrastructure/incomplete test execution; no receipt.

## Verify offline

Copy `receipt.json`, `receipt-key.pub.pem`, and the entire `evidence/` directory
from `baseline/` or `candidate/` together. Authenticate the public key through
a trusted channel; a key supplied by the same untrusted party as the receipt is
not a trust anchor. With the CLI installed (no sandbox or Git repo needed):

```sh
workflo verify /path/to/proof/receipt.json --pubkey /path/to/trusted/receipt-key.pub.pem
```

The result reports verification separately from the QA verdict. Check the printed
full commit against the one you intended. A verified failing check still returns
0 from `verify`. No bundle, missing teardown, changed files, a different run's
bundle, or a wrong key makes verification fail. `--evidence` can point to a
relocated bundle. Legacy `run`, `/v1`, and receipt v1–v4 verification are unchanged.

## What is bound and what is not

The built-in execution policy is validated and resolved before provisioning and
its twelve component digests are bound to the run. The fixed argv runs under
bubblewrap with a read-only snapshot and image, an empty-by-default environment,
required Landlock/seccomp, a pre-exec cgroup join, and a sealed anonymous
network namespace. There are no named network endpoints or model capabilities.
The supervisor observes the process scope/cgroup and verifies removal of the
workspace and the raw test report. It does not claim to have stopped a VM or
wiped a VM disk.

The host signs a development-only receipt v5 (Ed25519 over DSSE pre-authentication
encoding) after independently re-reading the proof. The key is generated outside
the guest after teardown and is not persisted. The bundle contains the admitted
RunSpec and policy, a per-file snapshot hash manifest, normalized test results,
scoped findings, the teardown record, and a canonical v2 ledger anchored by its
head and event count. The verifier re-derives the file inventory, byte digests,
ledger and finding/outcome bindings. Source bytes, raw logs, raw reports, and
private keys are not in the proof. The operator manages retention and sharing.

This is an attestation by a **trusted local operator** of what that development
run observed. It does not prove the test code is honest, the fix covers all
responses, the environment cannot be escaped, or that deletion securely erases
storage. The proof does not reconstruct or inspect the source or runtime bytes
independently. The sample does not evidence a hosted privacy boundary, a real
provider migration, or mapping precision/recall. Owner ratification, Firecracker
Gate B, and the protected release gates remain separate.
