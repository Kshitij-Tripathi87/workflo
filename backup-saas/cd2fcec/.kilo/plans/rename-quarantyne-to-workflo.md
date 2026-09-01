# Plan: Rename `quarantyne` → `workflo` across the codebase

## Goal
Replace every occurrence of "quarantyne" (case-insensitive) with "workflo" across
tracked source/config/docs. The acronym appears in: a Python import package
(`quarantyne_executor`), two distribution names (`quarantyne-executor`,
`quarantyne-probe-engine`), a docs folder (`docs/quarantyne/`), author names,
prose, a test stdout marker, and an install script path reference.

## Scope — what renames to what

| Thing | From | To |
|---|---|---|
| Python import package (sandbox-executor) | `quarantyne_executor` | `workflo_executor` |
| Package source directory | `apps/sandbox-executor/src/quarantyne_executor/` | `apps/sandbox-executor/src/workflo_executor/` |
| Distribution name (sandbox-executor pyproject) | `quarantyne-executor` | `workflo-executor` |
| Distribution name (probe-engine pyproject) | `quarantyne-probe-engine` | `workflo-probe-engine` |
| Author name (pyproject `authors`) | `Quarantyne` | `workflo` |
| Docs folder | `docs/quarantyne/` | `docs/workflo/` |
| Docs folder reference in prose/path | `docs/quarantyne/sandbox_contract.md` | `docs/workflo/sandbox_contract.md` |
| "The Quarantyne sandbox executor" / "for Quarantyne" prose | `Quarantyne` | `workflo` |
| Test stdout marker | `QUARANTYNE_REPORT:` | `WORKFLO_REPORT:` |
| Egg-info dirs (gitignored, but stale) | `...egg-info/sandbox_executor.egg-info` | delete so setuptools regenerates cleanly |

**Already correct (no change needed):**
- `apps/sandbox-executor/src/quarantyne_executor/__init__.py` docstring already says "workflo sandbox executor" — only its import statements need the rename.
- `docs/quarantyne/sandbox_contract.md` title already says "workflo Sandbox Contract" — only the path reference inside it (line 26) and the folder name need renaming.
- The probe-engine's *import* package is `probe_engine` (no quarantyne prefix) — only its *distribution* name in pyproject needs renaming.

## Out of scope (do NOT touch)
- `packages/npm-workflo/.venv/` — gitignored, generated virtualenv; leave alone.
- `apps/sandbox-executor/build/`, `packages/probe-engine/build/` — gitignored build artifacts; leave alone (regenerated on next build).
- `packages/npm-workflo/vendor/*.whl` — built wheel artifacts; the postinstall.js references them by filename. These wheels are NOT renamed (they're build outputs); only the *filenames listed in postinstall.js* will be updated to the new distribution names so the next wheel build matches. Per-file note below covers the ambiguity.
- The 3 `receipt*.json` / pubkey fixtures at repo root and `verify-test-*` — these contain `WORKFLO_REPORT`/`WORKFLO_CANARY` markers already (the WORKFLO_ prefix predates this), plus are gitignored receipts; leave alone.
- `tenant_shield`, `tenant_shield_worker`, `tenant_shield_schema`, `airlock-sandbox-isolation`, `workflo-cli`, `workflo_ai` — these are *other* names in the repo and not "quarantyne"; do not mistake them.
- The `main.py.tmp` scratch file (`apps/workflo-cli/src/workflo_cli/main.py.tmp`) — it's an untracked temp file; update it for consistency with `main.py` since both were found, but note its `.tmp` status.

## Detailed steps

### Step 1 — Rename the sandbox-executor Python package directory
`git mv` the directory so history is preserved:
`apps/sandbox-executor/src/quarantyne_executor/` → `apps/sandbox-executor/src/workflo_executor/`

Then update the 5 files inside it:
- `workflo_executor/__init__.py` — fix the 2 `from quarantyne_executor...` imports.
- `workflo_executor/executor.py` — fix the 2 imports at lines 75, 79.
- `workflo_executor/runtime.py` — fix the import at line 23.
- `docker_runner.py` — no quarantyne refs (verified; skip).
- Delete the now-empty/stale `quarantyne_executor.egg-info` directory (gitignored, but stale; deleting avoids confusion). Use `Remove-Item -Recurse -Force`.

### Step 2 — Update sandbox-executor pyproject.toml
File: `apps/sandbox-executor/pyproject.toml`
- `name = "quarantyne-executor"` → `name = "workflo-executor"`
- `description = "The Quarantyne sandbox executor — ..."` → `description = "The workflo sandbox executor — ..."`
- `authors = [{ name = "Quarantyne" }]` → `authors = [{ name = "workflo" }]`

### Step 3 — Update probe-engine pyproject.toml
File: `packages/probe-engine/pyproject.toml`
- `name = "quarantyne-probe-engine"` → `name = "workflo-probe-engine"`
- `description = "Generalized, config-driven probe engine for Quarantyne — ..."` → `"...for workflo — ..."`
- `authors = [{ name = "Quarantyne" }]` → `authors = [{ name = "workflo" }]`

### Step 4 — Move the docs folder
`git mv docs/quarantyne docs/workflo`

Then update the moved file `docs/workflo/sandbox_contract.md` line 26:
- `` `apps/sandbox-executor/src/quarantyne_executor/executor.py` `` → `` `apps/sandbox-executor/src/workflo_executor/executor.py` ``

### Step 5 — Update the workflo-cli main.py (and main.py.tmp)
File: `apps/workflo-cli/src/workflo_cli/main.py`
- Line 37: `from quarantyne_executor import SandboxExecutor` → `from workflo_executor import SandboxExecutor`
- Line 38: `from quarantyne_executor.executor import generate_sandbox_id` → `from workflo_executor.executor import generate_sandbox_id`
- Line 572 (inside a function): `from quarantyne_executor.executor import (...)` → `from workflo_executor.executor import (...)`

File: `apps/workflo-cli/src/workflo_cli/main.py.tmp` (scratch file, kept in sync)
- Lines 37, 38, 531: same `quarantyne_executor` → `workflo_executor` import renames.

### Step 6 — Update workflo-cli pyproject.toml dependencies
File: `apps/workflo-cli/pyproject.toml`
- `"quarantyne-executor"` → `"workflo-executor"`
- `"quarantyne-probe-engine"` → `"workflo-probe-engine"`

### Step 7 — Update control-plane app/api/v1/runs.py + pyproject.toml
File: `apps/control-plane/app/api/v1/runs.py`
- Line 77: `from quarantyne_executor import SandboxExecutor` → `from workflo_executor import SandboxExecutor`

File: `apps/control-plane/pyproject.toml`
- `"quarantyne-executor"` → `"workflo-executor"`

### Step 8 — Update worker-engine pyproject.toml dependencies
File: `apps/worker-engine/pyproject.toml`
- `"quarantyne-probe-engine"` → `"workflo-probe-engine"`

### Step 9 — Update all test files (import paths + the stdout marker)
These test files import `quarantyne_executor` and/or `patch("quarantyne_executor...")`:

| File | Treatment |
|---|---|
| `apps/workflo-cli/tests/test_cli.py` | Replace **all** `quarantyne_executor` → `workflo_executor` (lines 49, 116, 187, 252, 323, 609, 691, 695, 702, 703, 718, 719, 874, 943, 1000) plus the docstring "exported from quarantyne_executor" → "exported from workflo_executor". Use `replaceAll`. |
| `apps/sandbox-executor/tests/test_executor.py` | Replace all `quarantyne_executor` → `workflo_executor` (imports + `patch(...)` paths). Also **line 244**: the test stdout fixture `container_stdout='QUARANTYNE_REPORT: {"total":1...}'` → `'WORKFLO_REPORT: {"total":1...}'` (this is the marker the executor parses, see Step 11). Also line 338 `image="quarantyne-worker:test"` → `image="workflo-worker:test"` (that's a *worker image name*, currently inconsistent with the codebase's real `workflo-worker:latest`; matches "quarantyne" and is a worker image ref so it renames). |
| `apps/sandbox-executor/tests/test_executor_image_selection.py` | Replace all `quarantyne_executor` → `workflo_executor` (imports + `patch(...)` paths, lines 37-39, 301-304, 523-526). Use `replaceAll`. |
| `apps/sandbox-executor/tests/test_executor_web_probes.py` | Replace `quarantyne_executor` → `workflo_executor` (lines 14, 19, 24). Use `replaceAll`. |
| `apps/control-plane/tests/test_web_run_integration.py` | `patch("quarantyne_executor.SandboxExecutor"...)` → `patch("workflo_executor.SandboxExecutor"...)` (lines 98, 143, 188). Use `replaceAll`. |
| `apps/control-plane/tests/conftest.py` | `patch("quarantyne_executor.SandboxExecutor")` (line 101 docstring) + `monkeypatch.setattr("quarantyne_executor.SandboxExecutor"...)` (line 110) → `workflo_executor`. Use `replaceAll`. |
| `apps/control-plane/tests/test_runs.py` | `patch("quarantyne_executor.SandboxExecutor")` (lines 129, 150) → `workflo_executor`. Use `replaceAll`. |
| `packages/sandbox-isolation/tests/test_verifier.py` | Docstring line 1: "without trusting Quarantyne" → "without trusting workflo". Single-string edit. |

### Step 10 — Update the npm-workflo postinstall.js (venv-side, but tracked)
File: `packages/npm-workflo/scripts/postinstall.js`
- Lines 37-38: `"vendor/quarantyne_executor-0.1.0-py3-none-any.whl"` → `"vendor/workflo_executor-0.1.0-py3-none-any.whl"` and `"vendor/quarantyne_probe_engine-0.1.0-py3-none-any.whl"` → `"vendor/workflo_probe_engine-0.1.0-py3-none-any.whl"`.
- Note: the actual `.whl` files in `vendor/` are NOT renamed here (they're committed build artifacts matching the old names — renaming them is a build-output concern; the postinstall's pip install will fail until the wheels are rebuilt under the new names). This is the one place the rename is "wiring only, wheel rebuild deferred" — call it out in the summary.

### Step 11 — The `QUARANTYNE_REPORT` stdout marker (CRITICAL consistency check)
The executor parses worker stdout for a marker line. Verify which marker it expects:
- `apps/sandbox-executor/src/workflo_executor/executor.py` (post-rename) `_parse_run_report` looks for lines starting with **`WORKFLO_REPORT:`** (line 624 post-rename; verified in current file at line 624).

So the executor already expects `WORKFLO_REPORT` — meaning the test fixture at `test_executor.py:244` that emits `QUARANTYNE_REPORT:` is **already wrong / stale** (it would never match). Renaming that fixture line to `WORKFLO_REPORT:` is both the quarantyne→workflo rename AND a latent bug fix (verify with grep that no code expects `QUARANTYNE_REPORT`). 

**Pre-flight check before editing that test line:** grep the whole repo for `QUARANTYNE_REPORT` (case-insensitive) to ensure nothing emits it. If only the test fixture has it, it's safely renamed. If the worker-engine emits it anywhere, that worker code needs the rename too.

### Step 12 — Remaining prose/doc references
- `install.ps1` line 82: `docs/quarantyne/sandbox_contract.md` → `docs/workflo/sandbox_contract.md`
- `workflo-ai-integration/workflo-ai-integration/README.md` line 66: `docs/quarantyne/sandbox_contract.md` → `docs/workflo/sandbox_contract.md`
- `workflo-ai-integration/workflo-ai-integration/serving/.optional-gpu-path/README.md` line 24: `docs/quarantyne/sandbox_contract.md` → `docs/workflo/sandbox_contract.md`

### Step 13 — Delete stale egg-info + verify nothing stale lingers
- Delete `apps/sandbox-executor/src/quarantyne_executor.egg-info/` and `packages/probe-engine/src/quarantyne_probe_engine.egg-info/` (gitignored; stale after the package-dir rename. They'll regenerate on next `pip install -e .`.)
- Do NOT delete `packages/npm-workflo/.venv/Lib/site-packages/quarantyne_executor*` — gitignored venv; will be rebuilt by `npm-workflo/scripts/postinstall.js`.

## Verification

1. **Grep is empty:** `grep -ri quarantyne` (excluding `.venv`, `build`, `*.egg-info`) returns **zero** matches. This is the acceptance test for the rename.
2. **Python imports resolve:** The renamed package imports cleanly:
   ```powershell
   pip install -e apps/sandbox-executor
   python -c "from workflo_executor import SandboxExecutor, generate_sandbox_id; print('ok')"
   ```
   (Needs `packages/core-schema` + `packages/sandbox-isolation` installed too, per deps.)
3. **Test suites pass:** Run the test suites that were touched to confirm import paths are correct:
   ```powershell
   pytest apps/sandbox-executor/tests -v
   pytest apps/workflo-cli/tests -v
   pytest apps/control-plane/tests -v
   pytest packages/sandbox-isolation/tests -v
   ```
   The npm-workflo postinstall.js wheel rename can't be tested without rebuilding the wheels — flag this as a deferred follow-up in the summary, not a blocker.
4. **Grep double-checks for false positives:** after editing, re-grep `quarantyne` case-insensitive to confirm zero remaining tracked hits.

## Notes / risks
- The `.whl` files in `packages/npm-workflo/vendor/` keep the old `quarantyne_*` filenames; `postinstall.js` is updated to the new filenames, so a wheel rebuild is required before `npm install` works again (deferred — flagged in summary).
- The `main.py.tmp` scratch file is edited for consistency but it's a `.tmp` (likely a vim/editor swap); the canonical file is `main.py`. If `main.py.tmp` is unwanted it can be deleted, but deleting is not part of "rename quarantyne" — leaving it as-is content-wise after rename.
- This is a pure-rename pass: no behavioral changes except the latent `QUARANTYNE_REPORT` → `WORKFLO_REPORT` test-fixture fix (which aligns the fixture with what the executor already parses). No production runtime code is changed by the marker edit (the executor already expects `WORKFLO_REPORT`).
