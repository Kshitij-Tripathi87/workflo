# Workflo Trust MVP — Phase 0 reconciliation

- **Review base:** `571879b8d55d3a989697c8d385484c7967594c59`
- **Proposal:** [draft PR #14](https://github.com/Kshitij-Tripathi87/workflo/pull/14)
- **Decision status:** Ownership and inference policy are proposed. This review
  does not ratify [ADR-0015–0021](../adr/README.md) or pass a production release gate.

## Scope

One Workflo workflow: pin a repository revision, admit a policy, run deterministic
checks on a customer-controlled runner, collect evidence, verify teardown, then
sign and independently verify a receipt. Start with the CLI; build the dashboard
and first GitHub integration on the same run/evidence contract after it works.
Use local or customer-owned infrastructure. Do not introduce a second dashboard,
new queue service, autonomous write-back, or new agent capabilities in Phase 0.
See [product boundaries](../../PRODUCT_BOUNDARIES.md) for repository ownership.

## What the draft needs to reconcile

| Area | Current checkout | Decision or work still needed |
| --- | --- | --- |
| Contract authority | [`workflo_schema.contracts`](../../packages/workflo-schema/src/workflo_schema/contracts/) already defines the ADRs' lifecycle, outcomes, policy, and evidence/receipt contracts. The control-plane attempt writer now derives terminal execution status from those types. | Keep the existing `/v1` status wire shape, the TS rebuild's legacy DB enum, and receipt v1–v4 verification as compatibility surfaces. Adopt the canonical graph at a versioned orchestration boundary; do not rename states in place. |
| Dispatch and tenancy | [`dispatch_service.py`](../../apps/control-plane/app/services/dispatch_service.py) persists run, attempt, and outbox together. Its worker adapter still calls `SandboxExecutor`; durability is not a proof of microVM execution. | Retain PostgreSQL for durable dispatch; no production in-memory queue. Wire authenticated customer runner claims to the outbox. Require real PostgreSQL role/RLS evidence, including `FORCE ROW LEVEL SECURITY` and a non-owner, non-superuser application role without `BYPASSRLS`. |
| Runtime boundary | [`worker/`](../../worker/) already has a Firecracker/jailer manager, admission, and typed guest-supervisor code. The [KVM suite](../../worker/tests/integration/test_kvm_boot.py) tests capability detection, not a real boot. | Continue in `worker/`, not a second Firecracker implementation under `apps/sandbox-executor`. Bind pinned runtime and guest artifacts and prove boot, isolation, resource limits, and independent teardown on real KVM before any strict release. No Docker/bwrap fallback. |
| User interface | `apps/dashboard` is a shell; `backend/` and `frontend/` serve the adjacent Cortex Autopilot product. | Use `apps/dashboard` once the CLI evidence workflow is established. Do not treat mock data as accepted Workflo results. |

The [real control-plane RLS test](../../apps/control-plane/tests/test_postgres_rls_integration.py)
is opt-in today; the default control-plane workflow does not provision its
PostgreSQL DSN. Make that test a non-skipping release gate and align its policy
assertions with the added `run_attempts` policy. The legacy TS database suite
is not a substitute for this test.

## Inference privacy inventory

The proposed rule is local inference for source-bearing work. Hosted BYOK, if
shipped, receives only explicitly authorized metadata through a schema-constrained
redaction gateway. Customer credentials alone do not authorize sharing source.
The current code does **not** establish that invariant end to end.

| Path | Treatment for the MVP |
| --- | --- |
| [`sandbox_runtime/planner.py`](../../packages/sandbox-runtime/src/sandbox_runtime/planner.py) and [`workflo_cli/llm_config.py`](../../apps/workflo-cli/src/workflo_cli/llm_config.py) | The compatibility planner can send prompts directly to a configured model endpoint, bypassing the hosted gateway. Keep that path out of the supported hosted profile; do not treat a provenance flag as enforcement. |
| [`workflo_worker/model/cloud_llm.py`](../../apps/worker-engine/src/workflo_worker/model/cloud_llm.py) | Standalone direct client remains in the tree; it is not called by the current default model stage. Do not wire it into release execution. |
| [`app/api/v1/inference.py`](../../apps/control-plane/app/api/v1/inference.py) | Existing hosted planner path constructs prompts from structured input. It is a starting point, not a proven BYOK privacy boundary. Require policy authorization and outbound payload assertions before release. |
| [`workflo_worker/model/`](../../apps/worker-engine/src/workflo_worker/model/) and [`workflo-ai-integration/`](../../workflo-ai-integration/) | The worker already owns llama.cpp startup and uses shared model routing/validation code. Consolidate that path without deleting required release tooling. Ollama is compatibility-only, not a release substitute or an automatic fallback. |

[P4 acceptance](../../P4_ACCEPTANCE.md) still requires the pinned GGUF/image run
and protected staging evidence. Neither the direct paths nor draft PR #2 should
be reintroduced as a shortcut to that gate.

## Contract checks

JSON Schema is generated from Python. The TypeScript lifecycle and outcome
mirrors are checked against the exports and shared golden records. Both are
Turborepo cache inputs, so a changed export or fixture invalidates cached parity
results. The tests exercise verified test failures, cancellation, and passing
checks with incomplete teardown as distinct results. The Python matrix checks
every legal and illegal edge and its authority; it does not imply that the
current dispatcher enforces all those transitions. The shared digest vectors cover the common safe-integer
subset; they do not change old ledger hashes or establish chain-v2 parity.

From the repository root with Python 3.11 and pnpm 9.12.0:

```sh
python -m pip install -r packages/workflo-schema/requirements-schema-export.txt \
  -e './packages/workflo-schema[dev]' -e ./packages/sandbox-isolation
python packages/workflo-schema/scripts/export_schemas.py --check
python -m pytest -q packages/workflo-schema/tests
pnpm install --frozen-lockfile
pnpm --filter @workflo/contracts test
pnpm --filter @workflo/events test
```

When intentionally changing a contract, run the exporter without `--check` and
review the generated diff with the corresponding model and mirror changes.

## Development golden workflow

Use the existing deterministic fixture repo created by
[`scripts/linux/setup_env.sh`](../../scripts/linux/setup_env.sh) at
`/root/wf-fixture`. The setup prints its reproducible commit ID. On a dedicated
Linux development host with the prerequisites in
[`linux-gate.yml`](../../.github/workflows/linux-gate.yml):

```sh
sudo -E bash scripts/linux/setup_env.sh
sudo -E bash scripts/linux/golden_run.sh
```

The test-tier harness runs the CLI against the fixture, produces a development
receipt and evidence, and independently verifies them. Keep the receipt,
public key, and evidence directory together. The harness exercises the
namespace profile, not Firecracker, production receipt v5, or hosted inference.
It does not replace the next slice's requirement to bind the exact source and
policy digests into a receipt.

## Follow-up and open gates

[Phase 1 implements the local development slice](PHASE_1_LOCAL_PROOF.md):
pin a commit and policy, run deterministic checks, verify teardown, and issue
an offline-verifiable development receipt without changing legacy paths.

Still open:

1. Owner ratifies the Workflo product boundary and Python contract authority;
   confirm the target runner and metadata-only hosted inference scope.
2. Run Gate B and the protected model/tenant release gates on their required
   platforms. Missing hardware, credentials, or release artifacts are blockers,
   not passing evidence or permission to widen the execution profile.
