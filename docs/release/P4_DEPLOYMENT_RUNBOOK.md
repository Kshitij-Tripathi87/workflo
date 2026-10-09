# Workflo P4 Deployment Runbook

**Environment:** staging / release candidate  
**Purpose:** deploy a private model endpoint and connect it to the existing observation-only Workflo inference gateway without granting the sandbox network access.

This runbook describes the deployment contract. It is not evidence that infrastructure has been provisioned. Record actual account, region, instance, model revision, image digest, deployed commit, and measured results during execution.

## 1. Target topology

```
GitHub Actions / developer host
          |
          | authenticated planner request containing bounded observations
          v
Workflo CLI + host-side planner
          |
          | HTTPS + run_tests API key
          v
Control plane: /v1/inference/plan
          |
          | private network; service-to-service auth
          v
Model server (OpenAI-compatible /v1/chat/completions)
```

The sandbox remains isolated using its existing `network_mode="none"`. The host-side planner returns tool proposals to the sandbox; the sandbox ToolGateway authorizes every action. The model endpoint is never directly reachable from repository code inside the sandbox.

Do not enable `NetworkMode.INFERENCE_ONLY`, add a sandbox network attachment, or relax default egress denial as a shortcut.

## 2. Resolve the serving artifact before provisioning

There are inconsistent candidates in the repository:
- CLI, planner, and control-plane defaults use `qwen3-4b-4bit`.
- `infra/vllm/docker-compose.yml` names `Qwen/Qwen2.5-Coder-7B-AWQ` and uses an ARM64-tagged vLLM image with AWQ/GPU flags.
- `workflo-ai-integration/serving/docker-compose.llamacpp.yml` refers to local GGUF base/adapter paths; the adapters are placeholders and the router is not integrated into the worker.

Do not treat these as interchangeable. The release owner must record one canonical choice:
1. exact model/artifact identifier and immutable revision or SHA-256;
2. actual quantization/container format (e.g. AWQ vs GGUF; do not infer it from "4-bit");
3. accelerator instance, GPU and memory, runtime image digest, max context, max concurrent sequences;
4. tokenizer/chat template, stop/JSON behavior, and licensing provenance;
5. measured startup time and peak GPU memory.

The current reference manifests are not proof that any one combination runs. Build and test the selected serving image in the chosen target architecture before deploying it.

## 3. Provision the model endpoint

1. Use a dedicated staging environment and a GPU-compatible instance/runner if required by the selected artifact. GPU quota and billing must be confirmed before launch.
2. Put the model host in a private subnet. Do not assign a public inference endpoint. Permit ingress only from the control-plane security identity / private subnet and the explicitly approved staging runner for benchmarks.
3. Install a pinned NVIDIA driver/container runtime and compatible serving image. Record its digest; do not deploy `latest` as the release identifier.
4. Mount weights read-only from an access-controlled location. Verify the downloaded artifact checksum. Keep caches, logs, request bodies, prompts, and repository content out of customer-source mounts.
5. Configure the server behind private HTTPS or service-to-service TLS with authentication. Store the server credential in the cloud secret manager. Never put it in compose YAML or process arguments that will be copied into logs.
6. Configure health/readiness checks. Readiness is true only after the selected model is loaded and a non-stub completion can be produced.
7. Set explicit max-context, timeout, concurrency, and memory limits. Start with concurrency 1; increase only after benchmark and memory stability.

The control-plane setting `UPSTREAM_LLM_BASE_URL` should identify the OpenAI-compatible API base ending in `/v1`, because the gateway appends `/chat/completions`. For the benchmark workflow, `WORKFLO_MODEL_BASE_URL` is the origin without `/v1`, because the harness appends `/v1/chat/completions`. Verify actual routing using a live request before collecting benchmark figures.

## 4. Configure the control plane safely

Set values in the environment/secret manager, not in a committed `.env`:
- `ENVIRONMENT=production` (or `PRODUCTION=true`)
- `JWT_SECRET`: random secret of at least 32 bytes
- `DATABASE_URL`: private PostgreSQL URL
- `RLS_ENABLED=true` after database schema/RLS readiness is confirmed
- `MASTER_KEK_HEX`: 32-byte KEK in the secret manager, until a KMS-backed provider is actually implemented and tested
- `UPSTREAM_LLM_BASE_URL`: private authenticated inference API base ending in `/v1`
- `UPSTREAM_LLM_API_KEY`: secret for the upstream endpoint
- `UPSTREAM_LLM_MODEL`: exact canonical model identifier
- `UPSTREAM_LLM_TIMEOUT`: bounded timeout appropriate to the run policy
- `TRANSPARENCY_LOG_PATH`: persistent append-only path for the staging transparency log if the current deployment uses the file-backed log

The startup guard must reject unsafe production settings. In addition, the production lifespan no longer treats `RLS_ENABLED=true` as proof: it verifies that the database is PostgreSQL, the runtime role is neither SUPERUSER nor BYPASSRLS, each required table has ENABLE and FORCE ROW LEVEL SECURITY, the tables are owned by a separate schema-owner role, and all eight expected policies exist. A broken schema blocks startup. Do not disable the guard to get the container running.

### One-time schema bootstrap and runtime-role separation

The Control Plane currently ships a reviewed SQLAlchemy metadata bootstrap rather than a versioned Alembic migration history. Run the one-off bootstrap with a **schema-owner/admin DSN** against the target database before starting the production API. Inside the published container, run from `/app` so the checked-in RLS SQL under `/app/db/rls` is available:

```bash
# One-off operation from the private deployment runner; do not bake this DSN
# into the runtime service's environment or deployment manifest.
docker run --rm --network <private-db-network> \
  -e DATABASE_URL="postgresql+asyncpg://<schema-owner>:<password>@<private-db-host>:5432/<database>" \
  -w /app <control-plane-image-digest> \
  python -m app.db.bootstrap_schema
```

The bootstrap creates any missing metadata tables and applies `apps/control-plane/db/rls/001_tenant_rls.sql`. The policy script is repeatable for the named policies. It is not a substitute for versioned schema migrations when the data model changes; add and verify the migration path before repeated schema evolution.

Create/use a separate runtime role with no superuser or RLS bypass privilege and no ownership of the protected tables. Example for a freshly provisioned database (run as the database administrator; replace all placeholder values):

```sql
CREATE ROLE workflo_runtime LOGIN PASSWORD '<strong-runtime-password>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE <database> TO workflo_runtime;
GRANT USAGE ON SCHEMA public TO workflo_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO workflo_runtime;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO workflo_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE <schema-owner> IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO workflo_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE <schema-owner> IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO workflo_runtime;
```

Set the service's `DATABASE_URL` to the runtime-role DSN only after the bootstrap and grants complete. Verify that the runtime role is not the table owner and run the service's startup validation. Keep the schema-owner DSN in a separate protected deployment secret; never place it in the runtime environment.

### Provision the first scoped client key

The unauthenticated development key endpoints are disabled once production posture is set. Create the first least-privilege key with the one-off provisioning module, using the schema-owner DSN and a short-lived protected output mount:

```bash
install -d -m 700 /run/workflo-bootstrap
# Ensure the host directory is writable only by the deployment operator and
# is owned by the image's non-root UID (10001) for this one-off container.
chown 10001:10001 /run/workflo-bootstrap

docker run --rm --network <private-db-network> \
  --mount type=bind,src=/run/workflo-bootstrap,dst=/run/bootstrap \
  -e DATABASE_URL="postgresql+asyncpg://<schema-owner>:<password>@<private-db-host>:5432/<database>" \
  -e RLS_ENABLED=true \
  -e MASTER_KEK_HEX="<64-hex-character-secret>" \
  -e WORKFLO_BOOTSTRAP_PROJECT_ID=default \
  -e WORKFLO_BOOTSTRAP_KEY_SCOPES=run_tests,read_reports \
  -e WORKFLO_BOOTSTRAP_KEY_FILE=/run/bootstrap/initial-key.txt \
  <control-plane-image-digest> python -m app.db.bootstrap_api_key
```

The command writes the raw API key to a mode-0600 file and reports only its metadata; it does not print the secret. Move that file's value into the approved secret manager, configure the staging client's `WORKFLO_GATEWAY_API_KEY`, verify an authenticated request, then delete the temporary file. Do not provision an `admin` scope for the model gateway.

The present code supports a static KEK; do not claim managed KMS integration until an actual KEK provider exists and is tested. Treat this as a restricted staging/release-candidate deployment until key rotation, backup/restore, and operational access control are verified.

Before exposing the control plane:
1. Run the one-off schema bootstrap with the separate schema-owner role, then start the app with the restricted runtime role and `RLS_ENABLED=true`.
2. Confirm startup passes its live catalog/policy verification; verify tenant-scoped read/write denial, API-key scope enforcement, audit events, and secret redaction.
3. Verify the liveness/readiness endpoints.
4. Ensure the database, Redis (if enabled), and model endpoint are private; terminate public TLS at an approved ingress.
5. Verify logs do not contain API keys, request bodies, observation content, source snippets, or model secrets.

## 5. Configure the CLI to use the gateway

Use a protected API key scoped to `run_tests`. Run these commands on the host/CI environment—not from inside the sandbox:

```bash
workflo config set-llm \
  --base-url "https://<control-plane-host>" \
  --api-key "<workflo-run-tests-api-key>" \
  --model "<canonical-model-id>" \
  --mode gateway \
  --gateway-url "https://<control-plane-host>"

workflo config get-llm
workflo config test-llm
```

The actual base URL/path must match the CLI gateway client implementation. Confirm that `test-llm` probes the gateway health route and that a real planner request reaches `POST /v1/inference/plan`.

Do not use `--mode direct` for the privacy acceptance run. Direct mode is a separate supported host-side path and must not be confused with the gateway privacy contract.

## 6. GitHub Actions staging environment

Create a protected GitHub Actions environment named `p4-staging`. Restrict who may run deployments and real-model benchmarks. The workflow `.github/workflows/p4-model-acceptance.yml` expects the following environment values:

| Name | Type | Requirement |
|---|---|---|
| `WORKFLO_MODEL_BASE_URL` | Variable | HTTPS origin of the model endpoint, without `/v1` |
| `WORKFLO_MODEL_NAME` | Variable | Exact served model name |
| `WORKFLO_GPU_HOURLY_USD` | Variable | Explicit hourly rate / amortized cost assumption, numeric and finite |
| `WORKFLO_MODEL_API_KEY` | Secret | Endpoint bearer credential |

The real-model workflow intentionally requires the typed confirmation `RUN-REAL-MODEL-TEST` and runs on a trusted runner labelled `p4-staging`. Provision that runner in the private route to the endpoint, lock its access down, and do not allow untrusted pull-request code to run on it. Requests can incur costs.

## 7. Required deployment smoke tests

Run these in order; preserve stdout/stderr and correlation IDs while redacting sensitive payloads.

1. **Model readiness:** authenticated `GET /health` and a minimal authenticated completion; record the real model/revision and token usage.
2. **Gateway authentication:** missing/invalid key → 401/403; valid `run_tests` key → accepted.
3. **Privacy contract:** source-bearing top-level keys, nested source-bearing fields, source-like observation text, and arbitrary raw prompts → rejected; secret-like observation content is redacted before upstream dispatch.
4. **Provenance:** request IDs, model identifier, input/output token usage, elapsed time and hashes are present; `source_code_included=false`.
5. **Failure mode:** stop the model endpoint or use an unreachable upstream → controlled 502/503/exit behavior; no fake success; receipt/report states the planner was unavailable.
6. **Sandbox boundary:** direct DNS/egress from inside sandbox remains denied, even while host-side gateway inference succeeds.
7. **Full run:** public repo URL → immutable SHA → real Linux isolation → application health → real gateway/model inference → governed tool calls → Judge → teardown proof → signed receipt → transparency inclusion proof → independent verifier `VALID`.
8. **Tamper tests:** altered event, receipt bytes, and transparency proof each become `INVALID`.

A gateway fake-upstream test does not satisfy items 1 or 7.

## 8. Benchmark protocol and cost reporting

Use the manually triggered P4 workflow after staging is healthy. Run at concurrency 1, 2 and 4 with warmup requests; repeat the benchmark at least three times on the same deployed revision. Preserve:
- git commit and run ID;
- model identifier/revision, image digest, accelerator SKU/GPU/VRAM, region and quantization;
- context/token limits, actual request count and concurrency;
- success/failure count, p50/p95/max latency, requests/s and output tokens/s;
- declared hourly cost assumption and estimated request cost;
- GPU utilization/memory and any throttling/restarts.

The hourly price supplied to the harness is an **assumption**, not an observed cloud bill. Compare the estimate with actual cloud billing separately. Never use a stub endpoint's output as a production benchmark.

## 9. Release rollback

Rollback is required before production-candidate approval.

1. Preserve the previous serving image digest, model artifact revision, deployment config and control-plane image digest.
2. On elevated 5xx/timeout rate, OOM/restarts, unexpected model output, privacy-test failure, or cost-limit breach, stop new real-model acceptance runs immediately.
3. Route gateway traffic to the last known-good model revision or disable hosted planning and return the existing controlled planner-unavailable error. Do not silently fall back to ungoverned direct requests.
4. Roll back control-plane/serving image by immutable digest. Do not overwrite a model artifact in place.
5. Preserve redacted health/audit diagnostics, deployment revision, receipt bundle and timeline. Never log source or secret payloads during incident handling.
6. Re-run health, auth/privacy, controlled-unavailable, sandbox-egress and receipt-verification smoke tests before reopening traffic.

## 10. Release evidence checklist

- [ ] Artifact identifier, immutable revision/checksum, quantization and serving-image digest recorded.
- [ ] GPU/instance SKU, region, network rule set and hourly price assumption recorded.
- [ ] Control-plane production startup guard passes with safe config; unsafe config fails closed.
- [ ] Database schema and tenant/RLS checks verified.
- [ ] Model endpoint private, authenticated, healthy and producing non-stub completions.
- [ ] Gateway privacy tests pass against actual captured outbound payload shape.
- [ ] Linux gate has a real successful GitHub Actions run with no integration skips.
- [ ] Full e2e receipt verifies independently from a clean environment.
- [ ] Tampered receipt/evidence/proof rejected.
- [ ] Real benchmark reports uploaded; cost assumptions clearly labelled.
- [ ] Rollback drill complete; previous immutable deployment retained.
- [ ] No unresolved P0/P1 in the shipping path.
