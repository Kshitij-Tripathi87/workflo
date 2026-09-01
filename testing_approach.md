# Testing Approach Documentation

## Architecture Decisions

### 1. Playwright Over Selenium

**Decision**: Chose Playwright over Selenium for UI automation.

**Rationale**:
- Native auto-waiting (`expect().to_be_visible()` retries automatically)
- Built-in device emulation (no separate Appium for mobile web)
- Network interception for API mocking
- Browser context isolation per test (clean state)
- Faster execution (single protocol, no WebDriver overhead)

### 2. Page Object Model (POM)

**Structure**:
```
tests/ui/pages/
├── base_page.py       # Shared waits, screenshots, navigation
├── login_page.py      # Login form interactions
├── dashboard_page.py  # Post-login verification
└── projects_page.py   # Project CRUD interactions
```

**Why POM**:
- Centralizes selector maintenance
- Tests read at a higher abstraction level
- Reduces duplication across test files
- Mobile pages extend base with device-specific selectors

### 3. API + UI Integration Strategy

Tests validate the same data through multiple layers:

```
API: POST /api/v1/projects ──> Creates project ──> Returns ID
                                │
UI: Navigate to /projects ──> Search by name ──> Verify details match API
                                │
Security: Other tenant tries GET ──> 403 Forbidden
```

**Benefits**:
- Catches backend-vs-frontend rendering mismatches
- API calls provide fast setup (no UI navigation for preconditions)
- Single test validates the full data path

### 4. Flaky Test Prevention Framework

| Technique | Implementation |
|---|---|
| Auto-retrying assertions | `expect(locator).to_be_visible()` — retries up to 5s by default |
| Load state waiting | `page.wait_for_load_state("networkidle")` — waits for all network requests |
| Dynamic content handling | `page.wait_for_function()` — polls JavaScript expressions |
| Spinner/skeleton handling | `wait_for(state="hidden")` on loading indicators |
| Navigation completion | `page.wait_for_url("**/dashboard**")` — glob pattern matching |
| Screenshot on failure | `pytest_runtest_makereport` hook captures page state |

### 5. Multi-Tenant Testing Strategy

**Challenge**: Each test runs in a specific tenant context, but must verify isolation.

**Solution**:
- `APIClient` carries `X-Tenant-ID` header on every request
- Security tests create two clients (one per tenant) in a single test
- Positive control test validates same-tenant access works
- UI tests verify that project cards show the correct company name

### 6. Mobile Testing Approach

**Layered Strategy**:
1. **Playwright device emulation** (fast, free, CI-friendly)
   - iPhone 14, iPad Pro viewports
   - Touch event simulation
   - Runs in every CI build
2. **BrowserStack real devices** (for release validation)
   - Real iPhone and Android devices
   - Actual touch interactions
   - Network conditions simulation
   - Runs nightly or on release branches

**Cost Optimization**:
- 90% of mobile bugs caught by emulation
- BrowserStack only for release candidates
- Run on lowest BrowserStack plan (parallel sessions limited)

### 7. Test Data Management

**Generation** (per test run):
```python
# data/factories/project_factory.py
ProjectFactory.generate()
# Returns: {"name": "Test Project a1b2c3d4", "description": "...", ...}
```

**Principle**: Every test generates unique data using UUID. This enables:
- Safe parallel execution (no shared state)
- Easy debugging (test_run_id in metadata)
- Automatic collision avoidance

**Cleanup**:
- API-based teardown in `finally` blocks
- Best-effort (doesn't fail test if cleanup fails)
- Scheduled DB cleanup for orphaned records (runs daily)

### 8. CI/CD Integration

```yaml
# GitHub Actions workflow (conceptual)
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements.txt
      - run: playwright install chromium
      - run: pytest -n 2 --shard=${{ matrix.shard }}/4
      - uses: actions/upload-artifact@v3
        with:
          name: test-reports
          path: reports/
```

**Sharding Strategy**:
- Tests split across 4 CI shards
- `pytest-xdist` within each shard (2 workers)
- Total 8 parallel sessions
- Integration marker runs last (depends on API)

**Feedback Times**:
- Smoke tests: < 2 minutes
- Full regression: < 15 minutes (8 parallel sessions)
- BrowserStack suite: < 20 minutes (nightly)

### 9. Reporting Strategy

**Allure Framework** provides:
- Test timeline and execution history
- Screenshots and logs attached to failed tests
- Environment info (browser, OS, viewport)
- Trends over time (flake rate, pass rate)

**CI Artifacts**:
- Allure HTML report
- Screenshots per failure
- Console logs for network errors
- JUnit XML for CI integration

### 10. Assumptions and Open Questions

**Assumptions Made**:
- Test accounts have 2FA disabled (except specific 2FA test)
- Test tenants are pre-provisioned with known credentials
- API returns project ID synchronously
- UI uses `data-testid` attributes for elements
- Staging environment is stable during test execution

**Open Questions**:
- What is the max parallel session limit on BrowserStack plan?
- Should test data be cleaned up via API or database?
- Is there a CI webhook to trigger tests after deployment?
- What is the retention policy for test reports?
- Do we need to test SSO (Okta/Azure AD) login flows?
