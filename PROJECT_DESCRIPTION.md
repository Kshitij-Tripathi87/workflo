# Workflo — Privacy-First Autonomous QA & Data Observability Agent

> **Hackathon category:** Agents That Do Real Work (with elements of Metadata-Aware Code Generation & Development)

## 📋 Summary

Workflo is an autonomous QA agent that reads codebase architectures and DataHub metadata to *understand what's connected to what*, then **takes real action**: it executes tests in isolated network-blocked Docker sandboxes, exercises live application routes, generates production-ready pytest tests from real schemas, and emits verifiable cryptographic receipts (`wf://receipts/...`) proving teardown and isolation without trusting Workflo's own code.

It works as a local CLI, a SaaS control plane, an isolated sandbox execution engine, a Kubernetes-deployed worker fleet, and a dashboard so the same agent serves developers, data teams, and enterprises.

## 🔑 What it does

1. **Reads Metadata & Schemas** — connects via GraphQL or DataHub MCP Server to pull dataset schemas, lineage edges, and ownership metadata.
2. **Executes in Network-Blocked Sandboxes** — spins up isolated ephemeral sandboxes (`--network none`, memory/CPU quotas, read-only root filesystems) to execute tests and security probes.
3. **Tool-Calling AI Agent (`--deep-test`)** — boots the application, exercises APIs/endpoints, captures live telemetry, and explains findings with structured rationale.
4. **Outbound Canary Isolation Block** — runs an active outbound connection test to verify network isolation; runs fail immediately if the canary succeeds.
5. **Independently Verified Teardown** — unmounts `tmpfs` mounts, destroys containers, verifies absence, and wipes inference states.
6. **Ed25519 Cryptographic Receipts** — signs execution digests so anyone can verify what happened (`workflo verify`) without trusting Workflo.

## 🎯 The Challenge It Solves

Teams ship regressions and broken contracts because:
- Schemas drift silently and break downstream consumers
- Testing environments leak data or access external networks
- Static linters only check syntax and cannot observe runtime behavior
- Compliance auditors need tamper-evident proof that code and privacy boundaries were preserved

Workflo turns testing and observability into *executable, cryptographically verifiable guarantees*.

## ⚙️ Technologies Used

| Layer | Tech | Why |
|---|---|---|
| Metadata & Contracts | DataHub (GraphQL + MCP) | The graph memory the agent inspects and validates |
| Sandbox Isolation | Docker + tmpfs + network policies | Enforces zero-retention ephemeral runtime |
| Cryptographic Receipts | Ed25519 + SHA-256 | Tamper-evident execution proofs |
| Agent Engine | Python 3.11 + Tool-Calling Loop | Dispatches commands, checks endpoints, explains verdicts |
| Web Probes | Playwright (Chromium) | High-fidelity frontend route validation |
| Control Plane | FastAPI + SQLAlchemy + OAuth RFC 8628 | Device authorization and SaaS management |
| Web Platform | React 19 + Three.js (WebGL) + Tailwind | Interactive 3D sandbox visualization and console |

---

## 📦 Repository Layout

- `packages/workflo-schema/` — shared Pydantic v2 models (RunSpec, TestResult, SignedReceipt)
- `packages/workflo-utils/` — structured JSON logging and configuration helpers
- `packages/workflo-datahub/` — DataHub integration: GraphQL + MCP client, inspector, test generator
- `packages/sandbox-isolation/` — ephemeral tmpfs lifecycle, network policy, Ed25519 signer & verifier
- `packages/probe-engine/` — security probes, contract test generator, web test runner
- `packages/workflo-auth/` — OAuth 2.0 Device Authorization Grant (RFC 8628) and secure credential store
- `packages/npm-workflo/` — global npm wrapper (`@workflo/qa` / `workflo`)
- `apps/workflo-cli/` — Click CLI (`workflo run`, `workflo auth`, `workflo verify`)
- `apps/control-plane/` — FastAPI SaaS backend (OAuth, runs, API keys, worker fleet)
- `apps/sandbox-executor/` — `ContainerRuntime` abstraction, tmpfs mounting, canary verifier
- `apps/worker-engine/` — Pytest runner, Playwright probes, AI tool-calling agent
- `client/` & `server/` — Canonical launch website with 3D WebGL sandbox hero, trial modal, and documentation

---

## 🚀 Quickstart

### 1. Local CLI Execution
```bash
# Run tests and security scan on a repo
workflo run --repo https://github.com/pallets/click.git --test --security

# Run AI agent deep test with live application execution
workflo run --repo https://github.com/pallets/click.git --deep-test --security

# Independently verify a signed receipt
workflo verify wf://receipts/0ec7-9b20
```

### 2. Run Automated Test Suite
```bash
# Backend merged capabilities & live E2E lifecycle test
pytest backend/tests/test_live_e2e_workflo.py backend/tests/test_merged_capabilities.py -v
```

---

## 📄 License

Apache License 2.0 / MIT — see `LICENSE` at the root of the repository.
