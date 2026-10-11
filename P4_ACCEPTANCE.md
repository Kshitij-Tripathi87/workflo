# P4 production-readiness acceptance

> Status as of 2026-10-11. A gate is marked proven only when its corresponding
> workflow or real execution has passed. Unit tests and scripted golden runs do
> not substitute for real-model acceptance.

## Release candidate

The latest complete gates 1–3 evidence was produced from exact commit
`bdf686ebdb0d53cc980d72acb7657f78960e6df2` on
`arena/bd73d1dd-workflo`. Later model-serving changes must produce fresh local
regression and GitHub evidence before that newer commit can be released.

## Gates

| Gate | Requirement | Current status | Authoritative evidence |
| --- | --- | --- | --- |
| 1 | Linux isolation, no skipped security checks, and verified teardown | **PROVEN at `bdf686e`** | `linux-gate.yml` run `38078306454` |
| 2 | Three portable proof bundles independently verify; receipt/evidence tampering is rejected | **PROVEN at `bdf686e`** | `golden-run-proof-bundles` from run `38078306454` |
| 3 | Planner protocol repeats the governed three-call behavior | **PROVEN at `bdf686e`** | planner/golden stages in run `38078306454` |
| 4 | Real llama.cpp/GGUF serving with immutable identities, exact adapters, active-worker routing, validation, and fail-closed handling | **IMPLEMENTATION COMPLETE; REAL-ARTIFACT EXECUTION UNPROVEN** | `.github/workflows/p4-gate4-real-artifacts.yml` now builds/publishes the bound image and asserts real evidence; no release GGUF/image inputs have been supplied and no real run has passed |
| 5 | Protected staging preserves privacy, authorization, teardown, provenance, metrics, reproducibility, rollback, and failure handling during representative real inference | **IMPLEMENTATION COMPLETE; PROTECTED RUN OPEN** | `.github/workflows/p4-model-acceptance.yml` implements the binding 14-job evidence contract, including a separate secret-free verifier and tamper matrix; environment values, runner, real artifacts, bootstrap workflow registration, and a passing run remain external prerequisites |

Repository CI and Docker CI also passed for `bdf686e` in run `38078306460`;
Worker, Control Plane, CLI Agent, and Workflo CLI workflows passed for the same
commit. These results do not prove gates 4–5 for later model-serving code.

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
  --build-arg WORKFLO_RELEASE_COMMIT='<40-character-release-commit>' \
  --build-arg BASE_GGUF_SHA256='<sha256>' \
  --build-arg TEST_GEN_GGUF_SHA256='<sha256>' \
  --build-arg REASONING_GGUF_SHA256='<sha256>' \
  --build-arg REPORTING_GGUF_SHA256='<sha256>' \
  -t workflo-worker-deep:release .
```

This build must be run with the real artifacts. A syntax-only or mocked build is
not acceptance evidence.

## Gate 5 protected staging

GitHub registers a manual workflow only when its workflow file exists on the
default branch. Before either protected dispatch, the release team must merge an
approved workflow-only bootstrap change to the default branch; that registration
change must not auto-run inference. The implementation PR remains separate and
is not opened until Gate 5 evidence passes.

First dispatch `.github/workflows/p4-gate4-real-artifacts.yml` with the exact
`release_commit` and `confirm_real_run=BUILD-REAL-GGUF-IMAGE`. It verifies the
real manifest, proves six negative builds fail closed, builds and publishes the
deep image by registry digest, binds its embedded `llama-server` and GGUF hashes
to the exact commit, runs real worker/reporting inference without a network or
published port, and asserts explicit teardown/no-Ollama evidence.

Then configure the resulting digest as `WORKFLO_LLAMACPP_DEEP_IMAGE` and
dispatch `.github/workflows/p4-model-acceptance.yml` with the same exact
`release_commit` and `confirm_real_run=RUN-REAL-MODEL-TEST`. The protected
`p4-staging` environment and `[self-hosted, linux, p4-staging]` runner provide:

- the current manifest, base llama.cpp image/model identity, all four GGUF paths
  and hashes, and the registry-pinned candidate deep image;
- HTTPS model and observation-only gateway origins, model identity, protected
  API keys, and a finite non-negative instance-hourly cost assumption; and
- `WORKFLO_PREVIOUS_LLAMACPP_MANIFEST`,
  `WORKFLO_PREVIOUS_LLAMACPP_DEEP_IMAGE`, and
  `WORKFLO_PREVIOUS_RELEASE_COMMIT` for the rollback drill.

The workflow implements the binding 14-job acceptance contract as thirteen
ordered protected steps plus one separate GitHub-hosted verification job. It
fails unless all of the following complete:

1. protected approval, exact-SHA checkout, and clean-worktree validation;
2. fail-fast validation of variables, secrets, HTTPS origins, finite cost,
   immutable current/previous images, distinct rollback identities, and all
   four real GGUF files;
3. networkless/read-only verification of the embedded `llama-server`, image
   labels, commit, model identity, and base/adapter hashes;
4. installation from only the exact checkout plus retained package, Python,
   commit, manifest, binary, and image identities;
5. real aggressive worker inference and a separate schema-valid reporting
   request, with no generated test or narrative body retained;
6. hardened Linux execution producing a metadata-only signed receipt and full
   evidence chain;
7. missing/wrong-key denial, four source-bearing request denials, observation
   redaction, and one valid observation-only gateway request;
8. three benchmark repeats at concurrency 1, 2, and 4 with per-request markers,
   zero cross-request leakage, timings, tokens, and classified errors;
9. an explicit metadata-only cost report derived from the protected hourly
   assumption and a recorded representative-run request count;
10. a deliberate loopback transport failure whose non-zero outcome is reduced
    to identities, counts, timings, and error classes;
11. rollback to a distinct previous manifest/image/commit pair followed by
    process, listener, container, cache, workspace, and no-Ollama teardown;
12. an explicit completeness/redaction scan using the actual staging secret
    bytes in memory, without retaining those bytes;
13. an always-run producer upload containing every partial or complete report;
    and
14. a separate GitHub-hosted job with no protected environment or staging
    secrets that downloads the producer artifact, verifies its digest index,
    receipt signature/evidence chain, acceptance semantics, and rejection of
    tampered image, base-model, adapter, and teardown identities before
    publishing the final evidence index.

The workflows share one non-cancelling concurrency group, so Gate 4 and Gate 5
cannot overlap. Never mutate a release manifest in place: create a versioned
manifest, publish an immutable deep image, and rerun both protected workflows.

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
