# Plan: Test `--test --security` Combination

## Goal
Validate that `--test` (surface tests) combined with `--security` works correctly, including:
- Flag parsing and validation
- Worker image selection
- Probe group composition
- Sandbox execution with both surface tests and security canary
- Report generation with security probe results

## Context
From code review:
- `--test` / `--surface` runs native pytest + basic smoke tests
- `--security` adds tenant isolation, network isolation, canary check
- Both flags are **composable** (can be combined)
- Only one functional tier may be selected; `--security` is independent
- `--security` requires `--start-command` and `--port` (or workflo.yaml fallback)
- Surface tier uses `workflo-worker:latest` image
- Security adds canary check (outbound request MUST fail in network=none container)

## Command Syntax
```bash
workflo run --test --security \
  --repo <git-repo-url> \
  --start-command "python app.py" \
  --port 5000 \
  --dry-run  # optional: validate without running
```

## Preconditions
1. Git repository URL pointing to a test project
2. App-under-test start command and port must be provided (via flag or workflo.yaml)
3. User must be authenticated (`workflo auth login`)
4. Docker must be available and operational

## Execution Steps

### Step 1: Dry-run Validation
```bash
workflo run --test --security \
  --repo https://github.com/example/test-repo.git \
  --start-command "python -m pytest" \
  --port 5000 \
  --dry-run
```
**Expected**: Plan printed to stdout, exit 0, no Docker/clone executed.

**Validates**:
- Flag parsing: `--test` and `--security` accepted together
- Config file loading overrides
- Mutual exclusivity (only one functional tier)
- Security requires start_command + port
- Auth status check

### Step 2: Actual Run
```bash
workflo run --test --security \
  --repo https://github.com/example/test-repo.git \
  --start-command "python -m pytest" \
  --port 5000
```
**Expected**: Sandbox runs, tests execute, receipt signed, results printed.

**Observables**:
- Stderr output shows: `Probe groups: test, security`
- Worker image: `workflo-worker:latest` (surface tier)
- Canary check result: `request_succeeded: False` (expected in isolated container)
- Test report: `passed/total` counts from pytest
- Receipt includes `dependency_install_had_network: False` (single-stage flow)

## Expected Behavior

### Probe Groups
```
probe_groups: ["test", "security"]
```
- `test` surface tier runs repo's pytest suite unfiltered
- `security` adds tenant isolation probes + canary

### Worker Image
```
Worker image: workflo-worker:latest
```
- Surface image (small, fast, no model weights, no browser)

### Canary
```
Canary passed (egress blocked): True
```
- Since container has network=none, outbound request to https://example.com should fail

### Test Results
```
Tests: X/Y passed
```
- X = passed, Y = total from pytest collection
- No collection_error expected for valid repos

### Receipt
- `SignedReceipt` with Ed25519 signature
- `teardown_proof` with container_removed=True, filesystem_removed=True
- `canary_check` with `request_succeeded: False`

## Potential Issues & Edge Cases

### 1. Missing start_command/port
If `--start-command` and `--port` are omitted, the CLI will try to read from workflo.yaml:
- If no workflo.yaml: `UsageError: --security requires start_command and port`
- If workflo.yaml present: values used as fallback

### 2. Combined with other tiers
- `--test --security --deep-test`: **Error** - only one functional tier allowed
- `--test --security --web`: **Error** - deep+web combination not supported (would need deep-web image)

### 3. Repo without pytest tests
- pytest will collect 0 tests, report `0/0 passed`
- May still succeed if canary passes (network isolation works)

### 4. Auth not logged in
- Exit 1 with message: "Not authenticated. Run `workflo auth login` first."

### 5. Docker not available
- Executor will raise RuntimeError during container create/start
- Caught by top-level exception handler, failure receipt signed

## Validation Checklist

After running `workflo run --test --security ...`, verify:

- [ ] Stderr contains `Probe groups: test, security`
- [ ] Stderr contains `Worker image: workflo-worker:latest`
- [ ] Canary result: `request_succeeded: False` (proves network isolation)
- [ ] Report shows test results (passed/total counts)
- [ ] Receipt signature validates against published pubkey
- [ ] `dependency_install_had_network: False` (single-stage flow)
- [ ] Container and filesystem torn down successfully
- [ ] Exit code 0 (success) or 1 (failure - but should still have valid receipt)

## Rollback / Teardown
- Docker containers and tmpfs are always torn down after run (even on failure)
- Receipt provides signed proof of execution
- No persistent resources left behind

## Next Steps After Validation
If the plan works as expected, subsequent plans could test:
- `--test --security --publish` (publish results to Cortex cloud)
- `--test --security` with various repo types (Python, Node, etc.)
- Performance comparison vs `--test` alone