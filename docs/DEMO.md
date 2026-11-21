# Workflo agent execution demo

This is the runnable demo for Workflo's current agent-execution path. It is designed to let the team test real sandbox lifecycle behavior, governed agent tools, model planning, evidence collection, and receipt verification without waiting for the production Firecracker image pipeline.

> **Execution profile:** Linux namespaces + bubblewrap (development/CI only). This demo does **not** prove Firecracker/KVM isolation and must not be used as evidence that Gate B or production agent execution has passed.

## Run a demo from GitHub Actions

After this workflow is merged to the default branch, team members can launch the deterministic demo without configuring a local Ubuntu/WSL2 environment:

1. Open [Actions → Agent execution demo](https://github.com/Kshitij-Tripathi87/workflo/actions/workflows/agent-execution-demo.yml).
2. Select **Run workflow** and choose `quick` (recommended), `task-spec`, or `scripted`.
3. Open the completed run and download the `workflo-agent-execution-demo-<run>` artifact.

The `quick` mode runs both complete flows. The artifact contains execution logs, signed receipts, public keys, and evidence bundles. The workflow checks that the expected receipt/evidence files exist; the demo driver itself runs independent `workflo verify` checks before reporting success.

This is still a development/CI execution profile using Linux namespaces and bubblewrap. It is suitable for testing the agent loop, governed tools, deterministic findings, evidence, and receipts. It does not certify the Firecracker/KVM production boundary. Do not upload customer source repositories or secrets to the GitHub-hosted demo runner.

## Start the demo

The supported quick path runs two complete executions:

1. **Task-spec mode:** the existing Workflo Explorer agent runs its deterministic five-step task inside the isolated runtime.
2. **Scripted-planner mode:** a local OpenAI-compatible scripted model plans tool calls; the sandboxed agent performs them through the same governed ToolGateway.

No external model API key is required for the quick demo.

### One-time setup

Run on Ubuntu Linux or Ubuntu under WSL2, from the repository root:

```bash
sudo bash scripts/linux/setup_env.sh
```

The setup installs the Linux development isolation dependencies, builds the trusted runtime tree at `/opt/workflo/workflo-worker`, installs the Workflo CLI and packages into `/opt/workflo/venv`, and creates the disposable fixture repository at `/root/wf-fixture`. Re-running setup recreates that dedicated fixture directory.

### Run both demo modes

```bash
sudo -E bash scripts/linux/demo_agent_execution.sh
```

The driver creates a new output directory, refuses to overwrite an existing one, executes both runs, and retains the run logs, receipts, public keys, and evidence bundles.

To run one mode only:

```bash
# Deterministic agent task, no model dependency
sudo -E bash scripts/linux/demo_agent_execution.sh --mode task-spec

# Scripted local planner driving the real in-sandbox agent
sudo -E bash scripts/linux/demo_agent_execution.sh --mode scripted

# A configured real model or Workflo inference gateway
sudo -E bash scripts/linux/demo_agent_execution.sh --mode model \
  --mission "Explore the app's main flows, test authentication errors, and report reproducible failures."
```

For a real-model run, configure the endpoint and key in the same root execution context used for the demo:

```bash
sudo -E /opt/workflo/venv/bin/workflo config set-llm \
  --base-url <endpoint> --api-key <key> --model <model>

sudo -E /opt/workflo/venv/bin/workflo config test-llm

sudo -E bash scripts/linux/demo_agent_execution.sh --mode model \
  --mission "Probe the application and investigate any reproducible API failures."
```

Use `--mode all` to run task-spec, scripted-planner, and configured real-model modes in sequence. The model mode fails rather than silently falling back when the configured endpoint is unavailable or the planner does not actually execute a governed tool call.

Other options:

```bash
sudo -E bash scripts/linux/demo_agent_execution.sh \
  --fixture /path/to/a-git-repository-with-app-py \
  --output-dir /root/workflo-demo-run-01
```

A custom fixture must be a Git repository with an `app.py` that can be started using `python3 app.py` and binds to port 3457. The fixture is snapshot-pinned before the run.

## What the demo exercises

```text
Workflo CLI
    |
    v
Supervisor: preflight -> source snapshot -> dependencies
    |
    v
Linux development isolation
  bwrap + namespaces + cgroups + seccomp (+ Landlock when available)
    |
    +---- deterministic pytest execution
    |
    +---- app under test
    |
    +---- Explorer agent (inside its own sandbox)
             |
             v
         ToolGateway
         - HTTP GET/POST to approved internal app hosts
         - bounded log read
         - bounded repository file list/read
         - allow/deny decision and tool-call record for every request
             |
             v
         bounded observations -> optional host-side planner
    |
    v
Deterministic Judge -> evidence ledger -> teardown verification
    |
    v
CLI-side Ed25519 receipt signing -> independent workflo verify
```

The task-spec demo's default agent task performs these checks:

- Requests the app root and health endpoint.
- Reads the app log and lists repository files through governed tools.
- Attempts an out-of-policy HTTP request; the ToolGateway must deny and record it.

The scripted planner also probes the fixture's known-bad `/checkout` route twice. The expected signed QA finding is `GET /checkout fails (HTTP 500)`, with distinct evidence references and healthy sibling routes as controls.

The default fixture includes an intentional, stable defect: `GET /checkout` returns HTTP 500 while the root and health routes remain healthy. The scripted-planner mode exercises the plan/observe/plan loop using a local scripted OpenAI-compatible endpoint: it checks the healthy controls, probes checkout twice, and attempts an out-of-policy egress request. The deterministic Judge must confirm the repeated checkout failure against the healthy controls; the demo then verifies the signed receipt. This proves the planner protocol, governed execution, and deterministic finding path, **not** the reasoning quality of a real language model.

The model mode uses the configured direct endpoint or Workflo inference gateway. The mission is bounded and secret-redacted. The planner receives bounded runtime observations; the source snapshot stays within the sandbox. The sandboxed ToolGateway remains the only path that can execute tools.

## Output and verification

By default, output is written under:

`/root/workflo-agentic-demo-<UTC timestamp>/`

Each mode directory contains the CLI logs and its run directory. The signed receipt and evidence bundle are verified by `workflo verify` before the mode reports success. For a model-planner run, the driver also checks that the signed `agent_activity.planner` field is `llm` and that at least one governed tool call was made.

A CLI exit code of `1` can represent QA findings; the receipt and teardown verification are still checked separately. Infrastructure failures, missing receipts, planner fallback, or failed receipt/evidence verification stop the demo.

Useful artifacts include:

- `receipt.json` — signed run result and bounded agent activity summary.
- `evidence/` — hash-chained event ledger and evidence manifest.
- `agent_tool_calls.jsonl` — detailed governed tool-call records, when included by the runtime profile.
- `run.stdout`, `run.stderr`, `verify.stdout`, `verify.stderr` — execution and verification diagnostics.

## What this demo does not prove

The demo uses bubblewrap and Linux namespaces. Those are development/CI execution profiles only. A successful run is useful for testing agent dispatch, tool governance, task lifecycle, QA, evidence, and receipts, but it is **not** a production microVM result.

The repository also contains an early Firecracker worker slice with a real jailer/VMM client, host-side vsock channel, guest capability handshake, fixed guest workload, and teardown verification seam. Its guest currently runs a fixed deterministic workload—not the full Workflo Explorer agent. The real KVM integration test still requires a prepared, digest-pinned guest kernel/rootfs and a KVM-capable host. Until the real boot, isolation, adversarial tests, and independent teardown evidence all pass, Gate B remains unproven and production admission must stay disabled.

## Development sequence after the demo

The next execution increments should be delivered as small working slices:

1. Turn the agent's current default task into an admitted, typed task plan with role/profile/tool/budget bindings.
2. Launch the registered Explorer runtime inside the guest image rather than the development bwrap environment.
3. Add guest-side agent/tool runtime packaging and the image build/provenance pipeline.
4. Connect agent task lifecycle and scoped capabilities over the real vsock channel.
5. Prove the complete agent workload, evidence collection, and teardown on a protected KVM runner.

This keeps the demo testable now while progressing toward the production microVM boundary without confusing a development sandbox with a microVM.
