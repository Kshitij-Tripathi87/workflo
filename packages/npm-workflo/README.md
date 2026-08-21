# @cortex/workflo

`workflo` — sandboxed code-testing agent that verifies specific claims about
a repository and produces an Ed25519-signed receipt for every run.

This package is a thin **distribution shim** (Option C): the Python engine
ships as prebuilt wheels inside `vendor/` and is installed into a
package-local venv by `postinstall`. No TypeScript rewrite of the engine.

## Requirements

- Node >= 18
- Python >= 3.11 on PATH (`python3`, `python`, or `py -3`)
- Docker Desktop running (needed for `workflo run`; not for `auth`/`verify`)
- Network access to PyPI at install time (one-time, for transitive deps)

## Install

```bash
npm install -g --allow-scripts=@cortex/workflo ./cortex-workflo-<version>.tgz
```

Notes:

- The `./` prefix matters: without it npm parses the tarball path as a
  GitHub `owner/repo` shortcut and tries SSH.
- `--allow-scripts=@cortex/workflo` is required on npm >= 11.17, which
  blocks lifecycle scripts for packages not yet on your allowlist. To
  allow it permanently:

  ```bash
  npm config set allow-scripts=@cortex/workflo --location=user
  ```

- The `@cortex` scope is not yet published to the npm registry; installing
  from the dist tarball is the supported path until the org exists.

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

## Rebuilding the vendored wheels

From this directory:

```bash
npm run pack:build     # python scripts/build-wheels.py && npm pack
```

Builds the six internal wheels in dependency order — `workflo-schema`,
`sandbox-isolation`, `workflo-probe-engine`, `workflo-executor`,
`cortex-auth`, `workflo-cli` — wipes stale artifacts first, and drops the
tarball into `dist/`.

Requires the Python `build` package: `pip install build`.

## Package smoke test

```bash
npm test    # structural checks: shim parses, exactly 6 expected wheels, no strays
```

## How install idempotency works

`postinstall` writes `.workflo-install.json` capturing the package version,
Python version, and SHA-256 fingerprints of all six wheels. If the marker
matches on a re-install, setup is skipped (~1s). Any change — new wheels,
new Python — triggers a clean venv rebuild rather than an in-place mix.
