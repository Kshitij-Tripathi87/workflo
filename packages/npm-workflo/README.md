# @cortexstudio/workflo

[![npm version](https://img.shields.io/npm/v/@cortexstudio/workflo.svg)](https://www.npmjs.com/package/@cortexstudio/workflo)
[![node](https://img.shields.io/node/v/@cortexstudio/workflo.svg)](https://www.npmjs.com/package/@cortexstudio/workflo)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`workflo` — sandboxed code-testing agent that verifies specific claims about
a repository and produces an Ed25519-signed receipt for every run.

This package is a **distribution shim**: the Python engine ships as prebuilt
wheels inside `vendor/` and is installed into a package-local venv by
`postinstall`. No TypeScript rewrite of the engine.

## Requirements

- Node >= 18
- Python >= 3.11 on PATH (`python3`, `python`, or `py -3`)
- Docker Desktop running (needed for `workflo run`; not for `auth`/`verify`)
- Network access to PyPI at install time (one-time, for transitive deps)

## Install

```bash
npm install -g --allow-scripts=@cortexstudio/workflo @cortexstudio/workflo
```

> **Note:** `--allow-scripts=@cortexstudio/workflo` is required on npm >= 11.17,
> which blocks lifecycle scripts for packages not yet on your allowlist. To
> allow it permanently:
>
> ```bash
> npm config set allow-scripts=@cortexstudio/workflo --location=user
> ```

Verify:

```bash
workflo --version
```

## First run

```bash
# 1. Authenticate (device flow; spawns a local auth server on :3001 if needed)
workflo auth login

# 2. Run the sandboxed pipeline against a repo
workflo run --repo https://github.com/psf/requests.git --test --security

# 3. Verify the signed receipt
workflo run ... -o receipt.json --pubkey receipt.json.pubkey.pem
workflo verify --receipt receipt.json --pubkey receipt.json.pubkey.pem
```

Probe groups are composable: `--test`, `--deep-test`, `--aggressive-test`
(pick one) plus independent `--security` and `--web`.

For `--deep-test` and `--aggressive-test`, configure a hosted LLM endpoint
(tested with qwen3-4b-4bit):

```bash
workflo config set-llm --base-url https://inference.example.com/v1 --api-key sk-...
workflo config test-llm
```

## CI/CD (GitHub Actions etc.)

Non-interactive auth uses a workspace-scoped **service token**:

```bash
workflo auth login \
  --service-token "$WORKFLO_SERVICE_TOKEN" \
  --workspace-id "$WORKFLO_WORKSPACE_ID"
```

GitHub Actions example (dry-run validation — no Docker, no secrets needed
since auth is only required for `--publish`):

```yaml
- uses: actions/setup-node@v4
  with: { node-version: "20" }
- uses: actions/setup-python@v5
  with: { python-version: "3.11" }
- run: npm install -g @cortexstudio/workflo
- run: workflo run --dry-run --repo . --test
```

To publish results to the cloud, add the two secrets
(`WORKFLO_SERVICE_TOKEN`, `WORKFLO_WORKSPACE_ID`) in the repo settings, then:

```yaml
- env:
    WORKFLO_SERVICE_TOKEN: ${{ secrets.WORKFLO_SERVICE_TOKEN }}
    WORKFLO_WORKSPACE_ID: ${{ secrets.WORKFLO_WORKSPACE_ID }}
  run: |
    workflo auth login \
      --service-token "$WORKFLO_SERVICE_TOKEN" \
      --workspace-id "$WORKFLO_WORKSPACE_ID"
    workflo run --repo . --test --publish
```

## What it does

Every `workflo run` executes inside an **ephemeral Docker sandbox**:

1. **tmpfs mount** — the repo's working tree lives on a RAM disk, never on host
2. **Network: none** — `--network none` blocks all egress (spoken: sealed)
3. **Canary check** — a forced outbound probe that MUST fail; if it succeeds,
   the run aborts and the receipt shows broken isolation
4. **Teardown proof** — container + tmpfs must be gone after the run, verified
   by outside-process checks (`docker inspect`, mount lookup)
5. **Signed receipt** — Ed25519-signed JSON with lifecycle events, teardown
   proof, canary results, and hash of what ran. `workflo verify` checks
   signature + teardown + canary offline or against the Cortex key directory.

## Versioning & provenance

Published with `--provenance` to npm. The receipt of every run can be verified
with the published public key.

## License

MIT
