# P4: 14-Day Testing and Deployment Release Plan

**Target release-candidate date:** 2026-10-23  
**Baseline:** `5ca61a4` as reported in the engineering handoff; working branch `p4/14-day-release`  
**Scope:** Workflo CLI, Linux sandbox/runtime, governed Explorer path, evidence/receipt verification, inference serving, and the minimum operational deployment needed to prove the product claim.

> This is a release plan, not a claim that the work below has already passed. Every gate must link to a real CI run, test report, benchmark report, deployment revision, or independently verified receipt.

## Release objective

By the deadline, demonstrate one end-to-end Workflo run against a public Git repository, using a real model endpoint and real Linux isolation, and verify the resulting receipt independently. Deploy a controlled staging/production-candidate inference service with authentication, observability, bounded cost, rollback, and documented operating procedures.

The core trust boundary remains unchanged:

- The repository is cloned and executed in the customer/CI execution environment.
- The model may receive only bounded, policy-filtered observations and task metadata. Repository source code must not be forwarded to hosted inference.
- The runtime—not the model—authorizes and performs tool calls.
- Findings require deterministic reproduction and a healthy control.
- Teardown evidence, signed receipt, and transparency proof must be independently verifiable.

## Release scope lock

### In scope

1. Correctness and security gates for active Workflo packages.
2. Real Linux isolation, egress-denial, application-boot, and teardown evidence.
3. A real-model Explorer run through the observation-only inference path.
4. Receipt, signature, transparency, and independent-verifier acceptance.
5. Model-serving deployment, health checks, metrics, secrets, cost guardrails, and rollback.
6. Staging acceptance, install/quickstart verification, operator runbook, and versioned release artifacts.

### Explicitly out of scope for this 14-day release

- Multi-region or automatic multi-GPU scaling.
- New agent families, new connector families, and unrelated product features.
- Broad monorepo reorganization or redesigning marketing pages while the product acceptance chain is unproven.
- Claiming a benchmark or security property that has not been measured in its target environment.

## Release blockers to resolve on Day 1

### B1. The selected llama.cpp/GGUF path is not yet deployable

The selected serving direction is llama.cpp with GGUF, CPU-first. GPU quota is not a prerequisite for that baseline. The current AI-integration Compose file expects a base GGUF plus three adapter GGUFs that are not present in the repository, uses a floating image tag, and its model_router module is not called from the active runtime. The optional vLLM manifest is a separate GPU experiment, not the default release target.

Before treating this as a deployable product path, freeze:
1. the exact base GGUF identifier, source, immutable revision/checksum, and chat template;
2. each adapter GGUF identifier/checksum, or an explicit release decision that adapter-backed features are out of scope;
3. the exact llama.cpp server image tag and architecture-specific digest;
4. the live runtime call site that routes the intended Workflo operation through model_router/safety_gate, plus tests against a real llama-server.

A base-model completion proves serving only. It does not prove the adapter-backed test-generation/reasoning/reporting features are wired or validated.


### B2. Serving-instance cost is an explicit input

The benchmark accepts a required --instance-hourly-usd assumption for CPU or GPU hosting. Record provider, region, instance/SKU, serving image digest, model and adapter checksums, quantization, context length, concurrency, and hourly rate. Cost-per-request figures are estimates derived from this assumption, not measured cloud spend.


### B3. Deployment credentials, artifacts, and private access are required

Before Day 2, confirm access to the private staging environment, model artifact storage, image registry, secret manager, deployment environment, and GitHub Actions environment/secrets. A GPU is not required for the selected CPU-first llama.cpp path, but the base GGUF, the release-scoped adapter artifacts, and a compatible CPU host are required. If the real GGUF artifacts or a private endpoint are unavailable by Day 2, mark the release date at risk; a stub endpoint is not real-model acceptance.


### B4. Inference architecture documents disagree

The code has a hosted gateway in `apps/control-plane/app/api/v1/inference.py` and a host-side gateway mode in `packages/sandbox-runtime/src/sandbox_runtime/planner.py`. The gateway is designed to accept bounded observations, construct prompts server-side, reject source-bearing fields/text, and return provenance. The sandbox itself can remain `--network none`; the host/control plane—not the sandbox—makes the upstream request.

However, `docs/workflo/sandbox_contract.md` and `workflo-ai-integration/README.md` still contain older claims that shared inference is not implemented, and the adapter router is not wired into the real worker. These must not be conflated:
- **Release candidate path:** exercise the existing observation-only gateway mode, only if its real endpoint and privacy tests pass; keep sandbox egress denied.
- **Not in this release:** switching the sandbox onto a non-isolated/custom inference network, integrating untrained LoRA adapters, or claiming the model-router adapter path is live.
- On Day 1, record the chosen execution mode (local Ollama or host-side gateway), model artifact/revision, exact base URL semantics, and evidence that the planner is actually configured for that mode. Documentation must match what the CLI executes.

The deadline is at risk if the deployment needs new in-sandbox network semantics rather than the existing host-side gateway.

## 14-day execution schedule

| Day | Date | Primary work | Exit evidence |
| --- | --- | --- | --- |
| 1 | Oct 10 | Freeze release scope; record base/adapter GGUF revisions and checksums, architecture-specific llama.cpp image digest, CPU staging host, serving-instance cost assumption, and rollback target. Capture current branch/CI baseline. | Short architecture decision record; no conflicting model defaults in the chosen release path; external dependencies named and owned. |
| 2 | Oct 11 | Make CI execute on the release branch. Run standard unit/type/build suites and the Linux gate. Fix failures in provisioning, package installs, missing runtime capabilities, YAML, or test collection. | Green CI run links; Linux gate has the minimum expected executed-test count and zero skips in the authoritative isolation suite. |
| 3 | Oct 12 | Close real Linux isolation defects. Validate namespace/cgroup/Landlock state, DNS and egress denial from inside the sandbox, and cleanup after both success and forced failure. | CI artifacts include JUnit reports, isolation ledger events, golden-run receipts, and teardown attestations. |
| 4 | Oct 13 | Run golden CLI acceptance against pinned public fixture repositories. Verify ref-to-SHA immutability, no network after clone, app health probe, and the receipt artifact set. | Successful tests-tier and application-tier runs; recorded SHA; repeatable commands and artifacts. |
| 5 | Oct 14 | Harden adversarial/negative paths: unauthorized tool call, attempted egress, forged finding, missing reproduction, model timeout/unavailable, altered receipt, forged transparency proof, and teardown residue. | Each negative path is an automated test with the required fail-closed outcome; no negative path is accepted merely because it was skipped. |
| 6 | Oct 15 | Deploy the selected llama.cpp/GGUF target to a private CPU staging endpoint. Pin the server image/model/adapter revisions, set health/readiness probes, authentication, resource/time limits, and request concurrency limits. | Endpoint reachable only through the approved private path; authenticated non-stub completion includes usage metadata; rollback target recorded. |
| 7 | Oct 16 | Connect the real Explorer/inference gateway. Enforce observation-only request schema, bounded prompts/context, token/time budgets, explicit model-unavailable behavior, and inference provenance in the receipt. | Integration tests prove source text is not sent; model ID/revision and token usage are recorded; outage produces a controlled failure, not a fake success. |
| 8 | Oct 17 | Benchmark the real llama.cpp endpoint at concurrency 1, 2, and 4 (or the safe CPU limit), with warmups and repeat runs. Compare latency, successful throughput, tokens/sec, error rate, and estimated unit economics. | Versioned JSON + Markdown reports, declared price assumption, environment details, and a documented capacity/cost decision. No synthetic result represented as a real measurement. |
| 9 | Oct 18 | Deploy the required CPU-side control-plane/gateway components to staging, if part of the chosen release topology. Configure PostgreSQL migrations/RLS, Redis if required, KMS/secrets, TLS, least-privilege IAM, backups, health/readiness, and request/audit correlation. | Fresh deployment passes startup guards and migrations; tenant-isolation and auth tests pass; secrets are absent from logs and repo. |
| 10 | Oct 19 | Execute the full live product path from a clean Linux runner: public URL → immutable SHA → sealed sandbox → app/tests → real Explorer inference → ToolGateway → event ledger → Judge → verified teardown → signed receipt → transparency proof. | One complete end-to-end run with non-stub inference and all expected artifacts. Findings are only confirmed when reproduction and control conditions pass. |
| 11 | Oct 20 | Independent-verifier and security day. Move the artifacts to a clean machine/workspace and verify without access to the producing process. Tamper with receipt/event/proof fixtures and verify rejection. Run dependency/image/secret scanning. | Independent verifier returns `VALID` for the honest bundle and `INVALID` for tampered bundles; all release-blocking findings resolved or explicitly accepted with mitigations. |
| 12 | Oct 21 | Staging soak and failure recovery: repeat runs, model timeout, gateway restart, DB/restart recovery, failed deployment, rollback, and observability/alert checks. | Runbook-backed recovery/rollback drill; no false-green health state; dashboards/alerts for availability, errors, latency, queue depth, tokens, GPU utilization, and spend limits. |
| 13 | Oct 22 | Release-candidate freeze. Validate install/upgrade paths on clean machines, docs, supported platform matrix, environment variables, privacy statement, retention behavior, support diagnostics, SBOM, image digests, and release checksums. | RC tag candidate, reproducible install, release checklist signed off, and no open P0/P1 in the shipping path. |
| 14 | Oct 23 | Final go/no-go review. Re-run required gates on the exact release commit, verify evidence bundle independently, publish the versioned CLI/images/docs and rollback pointer. | Signed-off release bundle containing commit/tag, CI links, SBOM/digests, real benchmark reports, sample receipt, verifier output, and operator/security runbooks. |

## Mandatory acceptance gates

### Gate A — repository and CI

- Frozen dependency installation succeeds from a clean checkout.
- Python lint/type checks and all selected Python suites pass without `|| true`.
- All three active Next.js applications type-check and build.
- Root workspace checks/tests pass.
- Dockerfiles build and compose manifests validate.
- `linux-gate.yml` is actually executed in GitHub Actions—not merely parsed locally.
- Authoritative isolation tests meet their minimum executed counts; unexpected skips fail the job.

### Gate B — sandbox and execution trust

- Ref is resolved to an immutable SHA and the checked-out tree matches it.
- Network/DNS denial is observed from inside the sandbox.
- Runtime records the applied isolation controls.
- App health is observed in the isolated namespace.
- Every tool request is mediated by ToolGateway; denied actions are in the ledger.
- Candidate findings require repeated reproduction and healthy-control evidence.
- Teardown proves that the run's cgroup/process/network namespace/mounts are gone.

### Gate C — real inference and privacy

- The endpoint returns a real completion from the selected model, not a stub.
- Requests are authenticated and bounded; timeouts and HTTP errors fail closed.
- The gateway constructs the model prompt from approved observation fields.
- An automated test checks that repository source/code blobs do not enter the inference request.
- Inference provenance records model/revision, request IDs, token counts, and elapsed time.
- No credentials, prompts with sensitive content, or source code are emitted to logs.

### Gate D — proof and release operations

- Honest receipt signature and transparency inclusion proof verify.
- Independent verification succeeds from a clean environment.
- Receipt/evidence/proof mutation is rejected.
- Startup rejects unsafe production configuration.
- Deployment has a tested rollback, health checks, alerts, documented secret rotation, and a database recovery plan.
- Release assets are immutable/versioned; `latest` is not the only traceable deployment identifier.

## Operating cadence and decision rules

- Every day ends with a short evidence review: commit(s), exact command/run URL, passed/failed/skipped counts, artifacts, blocker owner, next day's target.
- A failing required gate is not bypassed with a skip, `continue-on-error`, `|| true`, or a lower threshold introduced only to get green.
- Keep model-serving benchmark reports separate from stub tests and label them distinctly.
- No model, accelerator, networking, or deployment change is accepted without re-running its relevant acceptance gates.
- If a critical dependency is unavailable, record it as a blocked gate; do not describe the overall release as complete.

## Release evidence bundle

1. Git commit and release tag.
2. Passing CI job URLs, including real Linux isolation/golden runs.
3. JUnit reports and golden-run receipts.
4. Real-model benchmark JSON and Markdown plus declared instance-rate assumption.
5. One full-run receipt, signature, evidence ledger, teardown attestation, and transparency inclusion proof.
6. Independent verifier output for valid and tampered cases.
7. Container image digests/SBOM, deployment revision, rollback reference, and config schema.
8. Install/upgrade instructions, troubleshooting guide, incident/rollback runbook, and privacy/data-flow note.

## Current status at plan creation

Planning source states the local repository/type/build gates are green, the benchmark harness exists, and fail-closed startup/skip assertions have regression coverage. The actual Linux isolation workflow has **not yet been proven by a real CI run**, and real model inference has **not yet been executed against the production-intended endpoint**. Those are release gates, not paperwork.
