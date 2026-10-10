# Workflo llama.cpp integration

This package is the worker's active local-model router and generation-safety
boundary. The production release backend is **llama.cpp / `llama-server` with
GGUF artifacts**. It is not an Ollama or vLLM deployment.

The package is installable as `workflo-ai-integration` and is a dependency of
`apps/worker-engine`. Deep and aggressive worker stages call it through the
owned runtime in
`apps/worker-engine/src/workflo_worker/model/llamacpp_runtime.py`.

## Release contract

A release model set contains exactly:

- one base GGUF;
- `test-gen.gguf`;
- `reasoning.gguf`;
- `reporting.gguf`; and
- a digest-pinned llama.cpp image identity of the form
  `image@sha256:<64 lowercase hex>`.

Every GGUF is identified by SHA-256. The runtime verifies all four files before
starting `llama-server`, binds it to loopback, discovers the exact three
adapters, and tears down its process and ephemeral state when the worker stage
ends. Missing artifacts, hash drift, adapter drift, malformed generation,
unsafe paths, compilation failure, inference errors, or teardown failure fail
closed.

`test-gen` and `reasoning` may receive repository source because they execute
only against the worker-owned loopback server. Hosted planner requests remain
observation-only. Source, prompts, and generated test bodies are not projected
into release acceptance reports.

## Routing and validation

| Worker route | Adapter sequence | Validated output |
| --- | --- | --- |
| deep | `test-gen` | `WriteTestCall` |
| aggressive | `reasoning`, then `test-gen` | `ProposeInvariantCall`, then `WriteTestCall` |
| reporting API | `reporting` | `ReportNarrative` |

The router uses llama.cpp's OpenAI-compatible endpoint and structured-output
schema. Model output is still validated by Pydantic, path containment and
overwrite checks, AST policy, and Python compilation before a generated test is
written. Model text is never accepted as a finding merely because it parses.

## Repository layout

```text
src/workflo_ai_integration/
  model_router.py              adapter discovery, routing, structured generation
  schemas.py                   Pydantic output contracts
  safety_gate.py               path, expression, AST, and compile checks
serving/
  docker-compose.llamacpp.yml  hardened standalone serving shape
  model-artifacts.example.json versioned frozen-artifact template
  .optional-gpu-path/          non-release vLLM experiment
scripts/
  verify_artifact_manifest.py  image/path/content/runtime-config verification
  convert_peft_to_gguf.*       conversion helper; conversion tool must be pinned
```

The old Ollama modules remain in the worker only as an explicitly selected
`WORKFLO_MODEL_BACKEND=ollama` migration compatibility path. They are not the
release default, are not installed by the deep image, and are not accepted as
P4 real-model evidence. The optional vLLM material is likewise not a release
serving target.

## Freeze and verify artifacts

Copy `serving/model-artifacts.example.json` to a protected release location,
replace every placeholder with the canonical source, local relative path, and
SHA-256, then run:

```bash
python workflo-ai-integration/scripts/verify_artifact_manifest.py \
  /protected/model-artifacts.json
```

On the staging runner, bind the runtime environment to that same manifest:

```bash
python workflo-ai-integration/scripts/verify_artifact_manifest.py \
  "$WORKFLO_LLAMACPP_MANIFEST" --check-env
```

`--check-env` requires every `WORKFLO_LLAMACPP_*` image, model, path, and hash
value to exactly match the verified manifest.

## Build the deep worker

The GGUF files are intentionally ignored by Git. Stage them at the paths used
by `apps/worker-engine/Dockerfile.deep`, then build from the repository root:

```bash
docker build -f apps/worker-engine/Dockerfile.deep \
  --build-arg LLAMACPP_IMAGE='ghcr.io/ggml-org/llama.cpp:server@sha256:<digest>' \
  --build-arg WORKFLO_LLAMACPP_MODEL_ID='<frozen-model-id>' \
  --build-arg BASE_GGUF_SHA256='<sha256>' \
  --build-arg TEST_GEN_GGUF_SHA256='<sha256>' \
  --build-arg REASONING_GGUF_SHA256='<sha256>' \
  --build-arg REPORTING_GGUF_SHA256='<sha256>' \
  -t workflo-worker-deep:release .
```

The build fails before producing the release image if the upstream image is not
digest-pinned, an artifact is absent, a digest is malformed/mismatched, the
model ID is empty, or `llama-server` is missing.

`serving/docker-compose.llamacpp.yml` is available for an isolated standalone
server. It is gated by the manifest verifier, mounts artifacts read-only, drops
capabilities, sets a read-only root filesystem, and exposes no host port. It
deliberately does not persist prompt caches.

## Tests and real acceptance

Mocked unit and integration coverage:

```bash
pip install -e workflo-ai-integration
pytest -q workflo-ai-integration/tests
pytest -q apps/worker-engine/tests
```

Mocks do not satisfy the real-model release gate. The manual
`.github/workflows/p4-model-acceptance.yml` workflow must run on the protected
`p4-staging` runner with the frozen manifest, real GGUFs, executable
`llama-server`, HTTPS serving/gateway endpoints, protected API keys, and a real
instance-hourly cost. It exercises the active aggressive worker route plus a
structured-results-only reporting request, verifies teardown/provenance, checks
missing-key authorization and source rejection, and benchmarks concurrency
1/2/4. Its uploaded source-free reports are the acceptance evidence.

Until that workflow and the real deep-image build pass for supplied artifacts,
the implementation is ready for acceptance but real serving is **not proven**.
