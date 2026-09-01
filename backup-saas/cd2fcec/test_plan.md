# Test Plan — WorkFlow Pro B2B SaaS Platform

## 1. Scope

### In Scope
- Web application (Chrome, Firefox, Safari)
- Mobile web (iOS Safari, Android Chrome via BrowserStack)
- REST API endpoints for project CRUD operations
- Multi-tenant data isolation
- Authentication (login, 2FA, role-based access)
- Cross-browser rendering consistency

### Out of Scope (Phase 1)
- Native mobile apps (iOS/Android SDK)
- Performance/load testing
- Third-party integration testing (Slack, Jira, etc.)
- Email notification delivery

## 2. Test Levels

### Unit Tests
- Run by development team (pre-commit)
- Focus on business logic, validation, data models

### Integration Tests (This Suite)
- API + UI end-to-end flows
- API direct calls for setup/verification
- Playwright for frontend behavior validation
- Mobile viewport testing via Playwright device emulation

### Security Tests
- Tenant isolation (cross-tenant data access)
- Role-based permission enforcement
- Authentication bypass attempts

## 3. Test Environment

| Environment | URL | Purpose |
|---|---|---|
| Local | http://localhost:3000 | Development testing |
| Staging | https://company1.staging.workflowpro.com | CI/CD pipeline |
| Production | https://app.workflowpro.com | Smoke tests only |

## 4. Test Data Strategy

### Data Generation
- Unique project names per test run (UUID suffix)
- Factory pattern for consistent, valid data
- Randomized team members to avoid collision

### Data Cleanup
- API-based teardown after each test
- Scheduled cron job for orphaned test data (runs daily)
- `data-testid="*"` attributes for stable UI element selection

### Tenant-Specific Data
- Dedicated API tokens per tenant
- YAML fixture files for known company/user configurations
- Environment variable overrides for CI

## 5. Test Execution Strategy

### CI Pipeline Integration

```
Commit → Lint → Unit Tests → Integration Tests → Security Tests → Deploy
                                    ↓
                          BrowserStack Matrix
                        (Chrome, Firefox, Safari,
                         iPhone 14, Galaxy S23)
```

### Parallel Execution
- `pytest-xdist` with `-n 4` for local runs
- BrowserStack supports parallel sessions (plan-dependent)
- Test data UUID ensures no cross-test contamination

### Retry Strategy
- API calls: 3 attempts with exponential backoff (2s, 4s, 8s)
- UI assertions: Playwright auto-retries for 5-15s (configurable)
- Test-level: 1 rerun for known flaky tests via `pytest-rerunfailures`

## 6. Test Cases Summary

| Test Suite | Count | Markers | Priority |
|---|---|---|---|
| Login Tests | 5 | smoke, regression | Critical |
| Multi-Tenant Tests | 4 | regression | Critical |
| Integration Tests | 3 | integration | High |
| Security Tests | 5 | security | Critical |
| **Total** | **17** | | |

### Login Tests
- `test_standard_user_login`: Valid credentials → dashboard
- `test_login_form_validation`: Empty form → validation errors
- `test_login_invalid_credentials`: Wrong password → error message
- `test_login_redirect_when_already_authenticated`: Authenticated user → redirect
- `test_login_with_two_factor_auth`: 2FA flow → dashboard

### Multi-Tenant Tests
- `test_tenant_scoped_data_visibility`: User sees only own company data
- `test_tenant_cannot_see_other_tenant_projects`: Cross-tenant data invisibility
- `test_role_based_access_employee`: Employee permissions enforced
- `test_role_based_access_admin`: Admin permissions available

### Integration Tests
- `test_project_creation_flow`: API create → UI verify → isolation check
- `test_project_creation_mobile_accessible`: API create → mobile verify
- `test_project_creation_cross_browser`: API create → Firefox/Chrome verify

### Security Tests
- Cross-tenant read access (403/404)
- Cross-tenant list access (not in results)
- Cross-tenant modify access (403/404)
- Cross-tenant delete access (403/404)
- Same-tenant access (200 positive control)

## 7. Reporting

- Allure Framework for rich HTML reports
- Screenshot capture on test failure
- Console logs and HAR files on failure (BrowserStack)
- CI pipeline publishes reports as build artifacts

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Flaky tests due to network | False failures | Retry logic + networkidle waits |
| Test data pollution | Cross-test failures | UUID names + API teardown |
| BrowserStack cost | Budget overrun | Run only integration marker; use device emulation for most tests |
| Staging environment instability | Blocked deployments | Health check pre-test; skip if unavailable |
