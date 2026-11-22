# 04 — CLI, Installation and Configuration Specification

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)

## 1. CLI design principles

- Keep Python CLI as the canonical interface; the web app calls the same API/contracts.
- Use the existing Click application and preserve current commands/flags where safe.
- Make dangerous actions explicit and default to read-only behavior.
- Prefer commands that compose in scripts and emit stable JSON with `--json`.
- Use meaningful exit codes. Reuse the existing contract in `apps/workflo-cli/src/workflo_cli/exit_codes.py`; do not independently redefine codes in docs or the web app.
- Never imply that a run executed in a strict VM when the selected backend was development-only.
- Every command must be documented in `workflo --help` and have command-level integration tests.

## 2. Proposed command tree

This table is target UX, not a command list to implement all at once. Map new commands to existing command groups and avoid aliases that confuse `workflo config` and `workflo provider`.

| Command | Purpose | Priority |
|---|---|---|
| `workflo init` | Detect project; create canonical `.workflo/workflo.yaml` or offer non-destructive migration from legacy project config | Existing; harden |
| `workflo doctor` | Host/runtime/provider/project diagnostics | Existing; expand OS-specific checks |
| `workflo config show` | Show effective config with secrets redacted | Existing equivalent; normalize |
| `workflo provider list` | Show supported adapter catalogue | P1 |
| `workflo provider add` | Create a local/cloud provider profile | P1 |
| `workflo provider update` | Change endpoint/model/policy; key replacement uses secure prompt | P1 |
| `workflo provider test` | Test endpoint/auth/model capability | P1 |
| `workflo provider use` | Select default provider profile | P1 |
| `workflo provider profiles` | List configured profiles and active default | P1 |
| `workflo provider remove` | Revoke/remove profile and associated secret | P1 |
| `workflo runner status` | Show daemon, OS, backend eligibility and active run capacity | P1 |
| `workflo runner start` | Start background runner/daemon | P2 |
| `workflo runner connect` | Device-flow authentication and runner enrolment | P2 |
| `workflo runner disconnect` | Revoke or pause runner | P2 |
| `workflo source inspect` | Show git status, commit, changes, source exclusions and snapshot preview | P1 |
| `workflo run` | Execute RunSpec locally or via selected runner | Existing; consolidate |
| `workflo runs list` | List recent runs | P2 |
| `workflo status [RUN_ID]` | Show lifecycle state and current phase | Existing; preserve |
| `workflo logs RUN_ID` | Show bounded sanitized event/log summaries | P2 |
| `workflo report RUN_ID` | Render markdown/json/html report | P2 |
| `workflo evidence export RUN_ID` | Export proof bundle | P2 |
| `workflo verify` | Verify receipt/evidence offline | Existing; harden |
| `workflo inspect` | Inspect signed receipt, read-only | Existing; preserve |
| `workflo explain` | Explain evidence/findings, optionally model-assisted | Existing; clarify local/cloud restrictions |
| `workflo suggest-fix` | Produce advisory patch artifact | P3 |
| `workflo auth/login/logout` | User authentication | Existing; preserve |
| `workflo update` | Update CLI/runner with signature/digest verification | Existing; harden |

## 3. CLI command behavior

### 3.1 `workflo init`

- Detect project language, package manager, test runners, app start candidates and ports.
- Never execute package scripts or app entry points during detection.
- Prefer parsing manifests and known configuration files as data.
- Generate canonical `.workflo/workflo.yaml` only when no canonical or legacy project configuration exists. Do not write a repository-root `workflo.yaml` / `workflo.yml`.
- If legacy project configuration exists, display detected files and a migration preview. Do not create a competing file automatically.
- A confirmed migration must be explicit, atomic and non-destructive; it must leave every legacy file unchanged. Conflicts require user resolution; never infer precedence.
- Report detection confidence and ambiguous choices.
- Display exact proposed check command argv and app command for user review.
- Do not add keys, install dependencies or modify package manifests.

### 3.2 `workflo doctor --full`

Report sections:

1. CLI version/update status.
2. OS/build/architecture.
3. Python/runtime dependencies, daemon status.
4. VM backend and hypervisor support.
5. Backend strict eligibility: pass/fail and individual reasons.
6. Guest artifact version/digests and signature status.
7. Storage/free space and resource capacity.
8. Network/firewall and DNS enforcement availability.
9. Provider profiles: local/cloud class, credential set/unset (never content), health result.
10. Control-plane connectivity/auth/runner enrollment.
11. Project config validity, source snapshot preview and policy digest.
12. Security gate/version and last real-host test result.

Exit 0 only if the requested profile is eligible. A developer might have a functioning CLI but no strict local backend; return nonzero for `doctor --profile strict` and show remote runner option.

### 3.3 `workflo source inspect`

Output:

- project path (local CLI only; never sent to cloud);
- repo root and HEAD commit;
- branch/ref metadata;
- staged/unstaged/untracked status;
- whether source snapshot includes uncommitted changes;
- file count / bytes by category;
- excluded paths with reason;
- symlink/submodule/LFS/secret-scan warnings;
- resulting deterministic snapshot digest (after build).

`workflo run --path .` must reject ambiguous dirty state unless the user explicitly selects `--commit-only` or `--snapshot-worktree`. If snapshots are produced for a dirty tree, record that fact in RunSpec/receipt.

### 3.4 `workflo run`

Proposed flags (reconcile with existing flags rather than break them):

```bash
workflo run \
  --path . \
  --profile strict \
  --mission "Test authentication and checkout" \
  --provider local-qwen \
  --check unit-tests \
  --check integration-tests \
  --agent \
  --api \
  --web \
  --output ./workflo-output
```

- `--profile strict|development|remote-strict`.
- `--provider PROFILE` chooses a preconfigured inference profile.
- `--mission` bounded, user-authored intent.
- `--check ID` selects declared checks; no freeform command unless explicit trusted config.
- `--agent` enables bounded agent planning.
- `--api`, `--web` choose tool sets; no arbitrary web navigation.
- `--dry-run` resolves the full plan but executes nothing.
- `--json` emits machine-readable lifecycle summary.
- `--output` points to a user-selected local artifact directory; avoid collisions/overwrite without confirm.
- `--timeout` may reduce run limits but not exceed org/project ceiling.

### 3.5 `workflo report`

Report should distinguish:

- requested vs resolved source identity;
- declared checks and what actually ran;
- execution/QA/trust outcomes;
- each finding's origin and confidence class;
- tests and probe aggregates;
- agent actions, denials and action budgets;
- model provider/mode and source policy;
- runtime backend and actual isolation profile;
- teardown checks;
- receipt signature/verification status;
- limitations / unverified claims.

Model explanation is labeled `AI interpretation`, with associated evidence references. The model cannot rewrite an observed fact in report.

### 3.6 `workflo suggest-fix`

- Read only from the run evidence and, in local mode, allowed source snapshot.
- Produce a unified diff file or patch artifact under user-selected path.
- Run `git apply --check` in a safe temporary copy, not against the original checkout.
- Show changed paths and patch digest.
- Never apply patch; no `--apply` in prototype.
- To validate fix, create a new run referencing the patch snapshot in isolated scratch.

## 4. Configuration layout

Use OS-appropriate config/data/cache paths via `platformdirs` (or existing platform-safe helper). Keep user-level configuration separate from project policy and runtime cache.

### 4.1 User settings

Example conceptual config:

```yaml
config_version: 2
active_provider_profile: local-qwen
profiles:
  local-qwen:
    provider: ollama
    endpoint_class: local_customer_controlled
    base_url: http://127.0.0.1:11434
    model: qwen3
    privacy_mode: local_source_context
    credential_ref: null
  openai-metadata:
    provider: openai
    endpoint_class: cloud
    base_url: https://api.openai.com/v1
    model: <configured-model>
    privacy_mode: metadata_only
    credential_ref: osvault://workflo/provider/openai-metadata
runner:
  control_plane_url: https://app.workflo.dev
  runner_id: <opaque-id>
  auto_start: true
```

Never store secrets in this file. It contains metadata and references only. For cloud BYOK, the control plane owns encrypted secret. For local provider key, the runner OS credential vault owns secret.

### 4.2 Project settings

Example `.workflo/workflo.yaml`:

```yaml
version: 1
project:
  name: sample-service
source:
  include: ["src/**", "tests/**", "pyproject.toml"]
  exclude: [".git/**", ".venv/**", "node_modules/**", "dist/**"]
checks:
  - id: unit-tests
    command: ["python", "-m", "pytest", "-q"]
    timeout_seconds: 600
app:
  start_command: ["python", "-m", "sample_service"]
  healthcheck:
    type: http
    port: 8000
    path: /health
agent:
  default_capabilities: [repo_metadata, tests, app_health, api, browser, logs, analysis]
  max_steps: 80
  max_duration_seconds: 600
resources:
  vcpus: 2
  memory_mib: 4096
  disk_mib: 8192
  wall_clock_seconds: 1800
network:
  default: deny
  allow: []
```

The parser must validate schema and deny unknown security-sensitive keys. The project may reduce available capabilities but cannot override organization policy or backend resource ceilings.

## 5. Config migration

Existing configuration file uses `~/.config/workflo/config.json` and `llm` object with `base_url`, `model`, timeout, direct/gateway mode. Existing `llm_config.py` has an OS credential store plus file-0600 fallback.

Migration requirements:

1. Detect old config path on all OS.
2. Parse known keys; do not silently discard unsupported options.
3. Create one provider profile preserving endpoint/model.
4. Translate `mode=gateway` to `endpoint_class=cloud` and `privacy_mode=metadata_only`.
5. Translate `mode=direct` only to local if endpoint can be proven loopback or explicitly configured customer-controlled. If remote host/unknown, mark profile `needs_review` and disable until user chooses safe classification.
6. Move key to OS vault or encrypted store; remove plaintext fallback only after migration success and explicit user message.
7. Keep compatibility `config get-llm` redacted and `config set-llm` alias during transition; it cannot configure direct cloud mode.
8. Add rollback/export of metadata-only config (no secrets).
### 5.2 Project configuration path and migration contract

The repository currently has three project-level configuration paths. The migration must preserve compatibility and must not create a fourth competing source of truth.

| Existing path | Current role | Target treatment |
|---|---|---|
| `.workflo/config.yaml` | Legacy project configuration path referenced by diagnostics/config helpers | Read-only migration input; map supported fields into the canonical file. |
| `.workflo/policies.yaml` | Policy defaults written separately by current `workflo init` | Merge into the canonical `policy` section only after schema validation; conflicts require explicit resolution. |
| Repository-root `workflo.yaml` / `workflo.yml` | Legacy input read by explicit `run --config` and selected web/security discovery | Preserve byte-for-byte. Support only as an explicitly selected compatibility input during the deprecation window. `init` must never create or overwrite this root-level file. |

**Canonical target:** `.workflo/workflo.yaml`. It contains project detection metadata, source selection, checks, application startup/health checks, agent defaults, policy defaults and non-secret inference-profile references. Provider credentials and API keys are prohibited in project YAML.

Migration behavior:

1. `workflo init` checks for the canonical file and all three legacy paths before writing. If any legacy path exists, it reports the detected files and offers a preview; it does not silently create a second configuration.
2. A migration preview lists every imported field, its source path, unsupported fields, validation warnings and conflicts. Dry-run mode writes nothing.
3. A confirmed migration writes the canonical file atomically, validates it against the versioned schema, and leaves every legacy file untouched. It does not delete, rename, or rewrite original files.
4. If legacy files define the same field differently, migration stops with a conflict report. Users must resolve conflicts explicitly; no implicit path ordering or precedence is allowed.
5. During the deprecation window, a root-level file is read only when selected through an explicit compatibility option such as `--config <path>`. Automatic discovery prefers the canonical file and refuses to merge it silently with legacy files.
6. Removing legacy readers is a separate breaking change after the migration utility and compatibility tests ship.

Acceptance tests cover canonical-only projects, each legacy path independently, all legacy paths with non-conflicting and conflicting values, malformed YAML, secrets in project configuration, interrupted atomic write, preservation of root config byte-for-byte, and repeat/idempotent migration.


## 6. Install and packaging

### 6.1 CLI installation channels

- Publish the Python package to a controlled package registry with versioned wheels/sdist, provenance/SBOM and checksum.
- Provide a one-line installer for Linux/macOS that pins release manifest and verifies signature/checksum before install.
- Provide signed Windows installer or `winget` package; install a Windows service/helper only when user opts into runner functionality.
- Support `pipx`/isolated Python install as an expert path.
- Do not require Node.js or pnpm for end-user CLI.
- Installer should install CLI only. Runner daemon and strict VM images are separate components with explicit platform prerequisites.

### 6.2 Update behavior

- Read signed release manifest.
- Verify downloaded artifact against manifest signature/checksum.
- Support current and previous release for rollback.
- Do not update VMM/guest image without coordinated compatibility check and migration path.
- Runner daemon reports version and upgrade-required status to dashboard.
- Rollback restores CLI/runner bundle and pins previous runtime artifacts; never silently reuse unknown VM image.

### 6.3 Uninstall

- Remove CLI/daemon binaries and service registration.
- Ask whether to remove runner identity and revoke remote enrolment.
- Clean caches and old runtime artifacts only after no runs are active.
- Preserve receipts/evidence by default; offer explicit delete/export.
- Remove provider credentials from OS vault on explicit removal.
- Do not delete user source or repository config.

## 7. Cross-platform command behavior

| Concern | Linux | macOS | Windows |
|---|---|---|---|
| Config/data path | XDG paths / `platformdirs` | Application Support / `platformdirs` | AppData / `platformdirs` |
| Secret store | Secret Service/libsecret if installed | Keychain | Credential Manager / DPAPI-protected store |
| Service manager | systemd/user service or foreground | launchd user agent or foreground | Windows service or foreground |
| CLI shell | bash/zsh/fish | zsh/bash/fish | PowerShell + CMD |
| VM backend | Firecracker/KVM | Virtualization.framework | Hyper-V |
| Local strict eligibility | Requires KVM + Gate B | Requires VZ entitlement/helper + Gate | Requires supported edition/Hyper-V + Gate |
| If backend unavailable | Remote strict runner | Remote strict runner | Remote strict runner |

The CLI must not shell out to Unix-only commands on Windows. Common logic uses Python platform APIs; native helpers have clear executable discovery, signature checks and JSON protocol.

## 8. CLI test requirements

- Snapshot of `--help` output for all command groups.
- Compatibility tests for current commands and exit codes.
- Config schema validation, old config migration, unknown key rejection.
- Credential store fake + platform integration test on OS runners.
- Ensure secrets absent from JSON output, errors, subprocess list, environment dump, logs and test artifacts.
- `init` does not modify project source.
- `source inspect` catches dirty worktree, symlink, untracked and ignored data.
- RunSpec is reproducible and deterministic.
- Dry-run never starts a process/VM or contacts provider.
- Strict mode rejects non-certified runtime; no silent fallback.
- Offline verify works without internet, Git repo, provider credentials or control plane.
- Upgrade/downgrade signature and compatibility tests.
- Upgrade/downgrade signature and compatibility tests.