# sample_repo — synthetic fixture repo for workflo worker-engine tests

This is a deliberately tiny, well-defined Python repo used by:

  * `apps/worker-engine/tests/test_executor_integration.py` — exercises
    deep-test model-stage plumbing by pointing the worker at this repo
    and mocking out Ollama.
  * `apps/sandbox-executor/tests/test_executor.py` — spot-references in
    integration-style tests where a real on-disk repo is needed.

## Layout

```
sample_repo/
  pyproject.toml      # editable-installable (no deps)
  conftest.py         # adds src/ to sys.path so tests import the package
  src/sample_pkg/     # 3 trivial functions (add, divide, is_host_blocked)
  tests/test_native.py  # 3 passing tests — surface baseline
```

## Surface vs Deep output (the contract)

| Tier       | Tests run                         | Expected outcome |
|------------|-----------------------------------|------------------|
| --test     | tests/test_native.py              | 3 passed |
| --deep-test| + tests/test_workflo_generated.py | 3 passed + N skipped (no API) OR N pass/fail against a live target |

The deep-test model stage writes `tests/test_workflo_generated.py` via
`ProbeGenerator.generate_pytest_file` → `ProbeRunner`. Those tests need
`WORKFLO_API_BASE_URL` pointing at an app-under-test booted with the same
`start_app_under_test` primitive `--web` uses. Without it they **skip**,
never silently pass.

**This fixture is NOT a multi-tenant API.** It cannot exercise cross-tenant
probes. The acceptance-test target is a separate probe-ready app (see
`tests/mock_server.py` — stdlib multi-tenant WorkFlow Pro-shaped mock,
no external deps).
