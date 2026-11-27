# Workflo — Software Change Verification

Workflo is a verification gate for software changes, including changes made by
AI agents. The [Trust MVP](docs/reconciliation/PHASE_0_WORKFLO_TRUST.md) targets
one workflow: run declared checks for an exact revision on a customer-controlled
runner, collect evidence, verify teardown, and issue an independently verifiable
receipt. A passing check, a successful execution, and verified evidence are
separate results.

**Current status: development preview.** The Docker and Linux namespace paths
are for local development and CI. Firecracker/KVM is the only approved target
for production execution of untrusted code; [Gate B](docs/adr/ADR-0022-microvm-boundary.md)
has not passed. Hosted source privacy and [real-model acceptance](P4_ACCEPTANCE.md)
are not established for the release candidate.

## Try the CLI from source

With Python 3.11+ and Git, run these commands from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e packages/workflo-schema -e packages/workflo-utils \
  -e packages/sandbox-isolation -e packages/sandbox-runtime -e supervisor \
  -e packages/probe-engine -e packages/cortex-auth \
  -e apps/sandbox-executor -e apps/workflo-cli

workflo --version
workflo run --path apps/worker-engine/tests/fixtures/sample_repo --test --dry-run
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1`. The dry run
validates the plan without launching a sandbox or running tests. Use
`workflo run --help` for execution options and platform prerequisites.

Try the [pinned integration-change demo](docs/reconciliation/PHASE_1_LOCAL_PROOF.md):
a mock provider changes its response contract, and the same checks verify a
failing baseline and a passing migration candidate. `workflo run-dev` uses the
Linux development profile and issues an offline-verifiable receipt v5. The
[legacy Linux golden run](docs/reconciliation/PHASE_0_WORKFLO_TRUST.md#development-golden-workflow)
remains available.
 
For an end-to-end agent execution demo (deterministic ToolGateway run plus a
scripted planner, with optional configured-model execution), see the
[runnable agent demo](docs/DEMO.md). After the demo workflow is merged to the default
branch, the team can launch the no-key quick demo from
[GitHub Actions](https://github.com/Kshitij-Tripathi87/workflo/actions/workflows/agent-execution-demo.yml)
and download the run artifacts. On Ubuntu/WSL2, run
`sudo bash scripts/linux/setup_env.sh` once, then
`sudo -E bash scripts/linux/demo_agent_execution.sh`. This exercises the
development namespace/bubblewrap path only; it is not Firecracker/KVM Gate B
evidence and does not enable production execution.


Given a receipt, its trusted public key, and its evidence bundle, verify offline:

```bash
workflo verify --receipt <receipt.json> --pubkey <receipt-key.pub.pem> --evidence <evidence-dir>
```

Verification checks the signed claims and available evidence. It is not proof
that the source has no defects, that no data was retained, or that a development
runtime meets the production isolation boundary.

## AI-assisted engineering workspace

The five-agent development plans, model benchmark evidence, repository ownership map,
task contracts and enterprise quality gates live in
[agent-workspace/README.md](agent-workspace/README.md). This workspace is for building
Workflo itself; it is separate from future customer-facing Workflo QA model providers.

## Where to contribute

- [Product boundaries](PRODUCT_BOUNDARIES.md) — Workflo ownership, compatibility paths, and the adjacent Cortex Autopilot product.
- [Architecture decisions](docs/adr/README.md) — accepted requirements and proposals pending ratification.
- [Phase 0 reconciliation](docs/reconciliation/PHASE_0_WORKFLO_TRUST.md) — contract checks, inference-path inventory, and remaining release gates.

## License

See [LICENSE](LICENSE).
