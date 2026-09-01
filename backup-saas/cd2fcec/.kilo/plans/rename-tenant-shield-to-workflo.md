# Renaming Plan: tenant-shield → workflo

## Overview
Rename the entire Tenant Shield project to "workflo" — all packages, modules, import paths, CLI commands, configuration, and documentation must have no remaining references to "tenant-shield", "tenant_shield", or "Tenant Shield".

## Affected Packages (rename each)

| Current Name | New Name | Key Files |
|---|---|---|
| `packages/core-schema` | `packages/workflo-schema` | `pyproject.toml` (name, description, authors, package discovery), `src/tenant_shield_schema/` → `src/workflo_schema/`, all `import tenant_shield_schema` → `import workflo_schema` |
| `packages/common-utils` | `packages/workflo-utils` | `pyproject.toml` (name, description, authors), `src/tenant_shield_utils/` → `src/workflo_utils/`, all `import tenant_shield_utils` → `import workflo_utils` |
| `packages/datahub-client` | `packages/workflo-datahub` | `pyproject.toml` (name, description, authors), `src/tenant_shield_datahub/` → `src/workflo_datahub/`, all `import tenant_shield_datahub` → `import workflo_datahub` |
| `packages/sandbox-isolation` | `packages/workflo-isolation` | `pyproject.toml` (add workflo-dependencies), imports from tenant_shield_schema/utils/datahub |
| `packages/probe-engine` | `packages/workflo-probe` | `pyproject.toml` (add workflo-dependencies), imports from tenant_shield_schema |
| `apps/control-plane` | `apps/workflo-control-plane` | `pyproject.toml` (name, description, authors, entry point), `app/main.py` FastAPI title/version, all `tenant-shield-*` references → `workflo-*` |
| `apps/agent-cli` | `apps/workflo-cli` | `pyproject.toml` (name, description, authors, entry point `workflo = "workflo_cli.main:cli"` → `workflo = "workflo_cli:cli"` or new module), `src/tenant_shield_agent/` → `src/workflo_agent/` or restructure, all import paths updated |
| `apps/worker-engine` | `apps/worker-engine` (keep or rename to `apps/workflo-worker`) | `pyproject.toml` (name/description), `src/tenant_shield_worker/` → `src/worker_engine/` or `workflo_worker/`, all internal imports updated |
| Root `pyproject.toml` | `name = "workflo"` | Change `name`, all `tenant_shield*` → `workflo*`, update package discovery includes, update `[project.scripts] tenant-shield = ...` → `workflo = ...` |

## Import Path Changes (representative)

| Old Import | New Import |
|---|---|
| `from tenant_shield_datahub.client import DataHubClient` | `from workflo_datahub.client import DataHubClient` |
| `from tenant_shield_datahub.generator import TestGenerator` | `from workflo_datahub.generator import TestGenerator` |
| `from tenant_shield_datahub.inspector import MetadataInspector` | `from workflo_datahub.inspector import MetadataInspector` |
| `from tenant_shield_datahub.models import DatasetSchema, ColumnInfo` | `from workflo_datahub.models import DatasetSchema, ColumnInfo` |
| `from tenant_shield_datahub.writeback import ResultWriteback` | `from workflo_datahub.writeback import ResultWriteback` |
| `from tenant_shield_utils.config import load_config, save_config` | `from workflo_utils.config import load_config, save_config` |
| `from tenant_shield_utils.logging import get_logger, configure_logging` | `from workflo_utils.logging import get_logger, configure_logging` |
| `from tenant_shield_schema.run_spec import RunSpec` | `from workflo_schema.run_spec import RunSpec` |
| `from tenant_shield_schema.results import TestResult, RunSummary` | `from workflo_schema.results import TestResult, RunSummary` |
| `from tenant_shield_schema.enums import Goal, RunStatus` | `from workflo_schema.enums import Goal, RunStatus` |
| `from tenant_shield.cli import main` | `from workflo.cli import main` (or apps/workflo-cli) |
| `from tenant_shield.reporting.compliance_report import ...` | `from workflo.reporting.compliance_report import ...` |
| `from tenant_shield.isolation import IsolationScenario` | `from workflo.isolation import IsolationScenario` |
| `from tenant_shield.adapters import ...` | `from workflo.adapters import ...` |

## CLI Command Renames

| Current Command | New Command |
|---|---|
| `tenant-shield --version` | `workflo --version` |
| `tenant-shield run ...` | `workflo run ...` |
| `tenant-shield report --results FILE` | `workflo report --results FILE` |
| `tenant-shield init --dir DIR` | `workflo init --dir DIR` |
| `tenant-shield auth login` | `workflo auth login` |
| `tenant-shield auth login` → stores in `~/.tenant-shield/` → `~/.workflo/` |

## Configuration Path Renames

| Old Path | New Path |
|---|---|
| `~/.tenant-shield/config.yaml` | `~/.workflo/config.yaml` |
| Config key `tenant.shield.*` | `workflo.*` |

## Documentation Renames (all "Tenant Shield" → "workflo", "tenant-shield" → "workflo", "tenant_shield" → "workflo")

- `PROJECT_DESCRIPTION.md` — entire file rewritten
- `README.md` — all references updated
- `docs/architecture.md` — all paths and names updated
- `docs/api_contract.md` — all `tenant_shield_schema.*`, `tenant_shield.*` → `workflo_schema.*`, `workflo.*`
- `docs/workflo/sandbox_contract.md` — all references updated
- `examples/generated-tests/` — test module headers auto-generated; update if desired
- `.kilo/plans/` — any plan files referencing old names

## DataFlow/API Contract Changes

- `api_contract.md` v1 endpoints unchanged (they reference `RunSpec`, `TestResult` models, not package names directly)
- But internal import paths in `apps/control-plane/app/api/v1/runs.py` `_execute_run` → update `from tenant_shield_schema.*` → `from workflo_schema.*`
- `X-TenantShield-Key` header → should this stay for backwards compat or rename to `X-Workflo-Key`? User to decide.

## Risks / Things to Watch

1. **Playwright test fixtures** in `tests/` reference `tenant_shield` pages → must update all page object imports
2. **Package discovery** in pyproject.toml `include`/exclude patterns must match new folder names
3. **External consumers** importing `tenant_shield_datahub`, `tenant_shield_schema` etc. will break — consider keeping old packages as `importlib` shims or deprecation aliases
4. **Docker images** referenced as `workflo-worker`, `workflo-worker-deep`, `workflo-worker-web` — keep these or rename consistently
5. **Receipt/signing keys** and config files with embedded old names must be updated or migration path provided

## Validation Checklist (after renaming)

- [ ] `python -c "import workflo_datahub; print('OK')"` works
- [ ] `python -c "import workflo_schema; print('OK')"` works
- [ ] `python -c "import workflo_utils; print('OK')"` works
- [ ] `workflo --version` runs without error
- [ ] `workflo auth login` functional
- [ ] All existing pytest tests still pass (imports resolved)
- [ ] No `ImportError: cannot import name ... from tenant_shield*` remains in any `.py` file
- [ ] No folder named `tenant_shield` remains anywhere under the repo root
- [ ] Documentation builds/links resolve without 404s on old paths

## Implementation Note

Per system instructions: **Do not perform actual file renames as this agent**. This plan file documents the complete scope. A human or implementation-capable agent should execute the actual edits using `sed`, `rename`, or IDE bulk-rename, respecting the `plan_exit` boundary. After plan_exit, the user can choose to implement the plan or keep the existing names.