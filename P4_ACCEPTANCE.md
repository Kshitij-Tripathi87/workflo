# P4 production-readiness acceptance

> Status as of 2026-10-10. A gate is marked proven only when its corresponding
> workflow or real execution has passed. Unit tests and scripted golden runs do
> not substitute for real-model acceptance.

## Release candidate

The gates 1–3 evidence was produced from release candidate
`e912905ea2c5618f0cba483c1b75735f206e9225` on `p4/14-day-release`.
Model-serving changes must land through a reviewed PR and produce new evidence
before that newer commit can be released.

## Gates

| Gate | Requirement | Current status | Authoritative evidence |
| --- | --- | --- | --- |
| 1 | Linux isolation, no skipped security checks, and verified teardown | **PROVEN at `e912905`** | `linux-gate.yml` run `37997223801` |
| 2 | Three portable proof bundles independently verify; receipt/evidence tampering is rejected | **PROVEN at `e912905`** | `golden-run-proof-bundles` from run `37997223801` |
| 3 | Planner protocol repeats the governed three-call behavior | **PROVEN at `e912905`** | planner/golden stages in run `37997223801` |
| 4 | Real llama.cpp/GGUF serving with immutable identities, exact adapters, active-worker routing, validation, and fail-closed handling | **IMPLEMENTED LOCALLY; REAL BUILD/RUN OPEN** | Tests cover the path; no release GGUF/image inputs have been supplied and no real image has been built |
| 5 | Protected staging preserves privacy, authorization, teardown, provenance, metrics, reproducibility, rollback, and failure handling during representative real inference | **OPEN** | `.github/workflows/p4-model-acceptance.yml` is implemented but not configured or run |

Repository CI and Docker CI also passed for `e912905` in run `37997223627`.
These results do not prove gates 4–5 for later model-serving code.

## Gate 4 contract

The only release serving target is llama.cpp / `llama-server` with GGUF
artifacts. Ollama and vLLM are not accepted as substitutes.

A frozen model set contains:

1. one base GGUF;
2. `test-gen`, `reasoning`, and `reporting` adapter GGUFs;
3. a canonical source and lowercase SHA-256 for each file;
4. a frozen model ID; and
5. an immutable llama.cpp image identity matching
   `image@sha256:<64 lowercase hex>`.

Use `workflo-ai-integration/serving/model-artifacts.example.json` to record the
set. The verifier checks the image pin, exact adapter names, safe local paths,
artifact contents, and—under `--check-env`—exact staging environment values:

```bash
python workflo-ai-integration/scripts/verify_artifact_manifest.py \
  /protected/model-artifacts.json --check-env
```

The worker-owned runtime verifies the same hashes before startup, permits only
loopback serving, discovers the exact adapters, validates structured output,
enforces generated-path and AST/compile policy, prevents overwrites, and fails
closed on inference or teardown errors. Signed receipt provenance records only
identities, hashes, request counts, elapsed inference, loopback/source scope,
and errors—not source or generated content.

The deep image is built from the repository root:

```bash
docker build -f apps/worker-engine/Dockerfile.deep \
  --build-arg LLAMACPP_IMAGE='<image@sha256:digest>' \
  --build-arg WORKFLO_LLAMACPP_MODEL_ID='<frozen-model-id>' \
  --build-arg BASE_GGUF_SHA256='<sha256>' \
  --build-arg TEST_GEN_GGUF_SHA256='<sha256>' \
  --build-arg REASONING_GGUF_SHA256='<sha256>' \
  --build-arg REPORTING_GGUF_SHA256='<sha256>' \
  -t workflo-worker-deep:release .
```

This build must be run with the real artifacts. A syntax-only or mocked build is
not acceptance evidence.

## Gate 5 protected staging

Dispatch `.github/workflows/p4-model-acceptance.yml` with
`confirm_real_run=RUN-REAL-MODEL-TEST`. The protected `p4-staging` environment
and `[self-hosted, linux, p4-staging]` runner must provide:

- `WORKFLO_LLAMACPP_MANIFEST`, executable `WORKFLO_LLAMACPP_BINARY`, frozen
  model ID/image, and base/adapter paths plus hashes;
- HTTPS `WORKFLO_MODEL_BASE_URL`, model name, protected API key, and a finite
  non-negative instance-hourly cost;
- HTTPS observation-only planner gateway and protected API key.

The workflow must fail unless all of the following complete:

1. the manifest, runtime environment, executable, paths, hashes, image pin, and
   cost assumption validate;
2. the representative calculator application runs through the active
   aggressive worker route (`reasoning` then `test-gen`);
3. generated tests pass structural/path/compile validation;
4. llama.cpp process/state teardown is verified and signed provenance has no
   inference error;
5. a missing gateway key is rejected with HTTP 401/403;
6. an authorized observation-only request returns model/request/hash/token and
   latency provenance without source;
7. a source-bearing gateway request is rejected without echoing its canary;
8. the real endpoint benchmark completes at concurrency 1, 2, and 4 and records
   latency, throughput, failures, token usage, cost assumption, commit, and
   runtime version; and
9. redacted reports upload even when a request fails, preserving failure
   evidence for diagnosis and rollback.

Rollback means returning deployment configuration to the last accepted frozen
manifest/image pair. Never mutate a release manifest in place; create a new
versioned manifest, rerun the deep-image build, and rerun protected acceptance.

## Required negative paths

| Scenario | Required result |
| --- | --- |
| Isolation unavailable or security tests skipped | Gate fails |
| Receipt/evidence bytes altered | Independent verifier rejects |
| Unauthorized tool or gateway request | Denied and recorded without secret/source echo |
| GGUF absent or hash changed | Manifest, image build, and runtime fail before inference |
| Image tag is mutable or digest malformed | Build/acceptance fails |
| Required adapter missing or extra adapter set configured | Runtime fails closed |
| Generated output has bad schema/path/AST/compile result | No test is written; stage fails |
| Inference records an error | Receipt semantic verification fails |
| Model process/state teardown is false or absent | Receipt semantic verification fails |
| Benchmark endpoint fails | Non-zero exit with partial redacted report retained |

## Local regression commands

Run project suites separately; several projects use the same top-level `tests`
package name and collide if collected in one pytest process.

```bash
pytest -q workflo-ai-integration/tests
pytest -q apps/worker-engine/tests
pytest -q apps/sandbox-executor/tests
pytest -q packages/workflo-schema/tests
pytest -q apps/workflo-cli/tests
pytest -q packages/sandbox-runtime/tests
```

These commands verify implementation regressions only. Gates 4–5 remain open
until the supplied immutable artifacts are built and the protected real-model
workflow succeeds on the exact release commit.
