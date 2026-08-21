"""
Integration Test: Project Creation Lifecycle

Testing Strategy:
1. Create project via API (fast, reliable)
2. Verify project appears in Web UI (Playwright)
3. Check mobile accessibility (BrowserStack emulation)
4. Validate tenant isolation (security boundary)

Data Strategy:
- UUID-based unique project names (parallel-safe)
- Factory pattern for test data generation
- API teardown for cleanup

Edge Cases:
- Network retry on API calls (3 attempts, exponential backoff)
- UI loading states (skeleton, spinner, debounced search)
- Mobile responsive navigation (hamburger menu)
- Cross-tenant security verification
"""

import os
import pytest
from playwright.sync_api import expect
from workflo.api.client import APIClient
from workflo.ui.pages.login_page import LoginPage
from workflo.ui.pages.projects_page import ProjectsPage
from workflo.mobile.pages.mobile_projects_page import MobileProjectsPage
from data.factories.project_factory import ProjectFactory
from workflo.isolation import assert_summary, verify_cross_tenant_access


def create_project_via_api(api_client, project_data):
    response = api_client.post("/api/v1/projects", json=project_data)
    response.raise_for_status()
    return response.json()


def delete_project_via_api(api_client, project_id):
    try:
        api_client.delete(f"/api/v1/projects/{project_id}")
    except Exception as e:
        print(f"Cleanup warning: Failed to delete project {project_id}: {e}")


def verify_tenant_isolation(api_client, target_tenant_id, project_id):
    """Cross-tenant read must be denied (403/404)."""
    intruder_client = APIClient(
        base_url=api_client.base_url,
        tenant_id=target_tenant_id,
        auth_token=api_client.session.headers.get("Authorization", "").replace(
            "Bearer ", ""
        ),
    )
    summary = verify_cross_tenant_access(
        api_client, intruder_client, project_id, include=["read"]
    )
    assert_summary(summary)


@pytest.mark.integration
def test_project_creation_flow(browser_context, api_client, env_config):
    """
    End-to-end: Create project via API, verify in UI, check tenant isolation.
    """
    # STEP 1: Create project via API
    project_data = ProjectFactory.generate(tenant_id=env_config.tenant_id)
    project = create_project_via_api(api_client, project_data)
    project_id = project.get("id")
    assert project_id is not None, "API did not return project ID"
    assert project["name"] == project_data["name"]
    assert project["status"] == "active", (
        f"Expected 'active', got '{project['status']}'"
    )

    # STEP 2: Verify project in Web UI
    email = os.getenv("TEST_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(browser_context)
    login_page.login_as(env_config.base_url, email, password)

    projects_page = ProjectsPage(browser_context)
    projects_page.navigate_to(env_config.base_url)

    card = projects_page.find_project_card(project_data["name"])
    assert card is not None, (
        f"Project '{project_data['name']}' created via API "
        f"but not visible in UI"
    )

    projects_page.open_project(project_data["name"])
    details = projects_page.get_project_details()
    assert details["name"] == project_data["name"]
    assert details["status"] == "active"

    # STEP 3: Tenant isolation — other tenant cannot access
    other_tenant = "company2" if env_config.tenant_id == "company1" else "company1"
    verify_tenant_isolation(api_client, other_tenant, project_id)

    # STEP 4: Same tenant CAN access (positive control)
    response = api_client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200

    # STEP 5: Cleanup
    delete_project_via_api(api_client, project_id)


@pytest.mark.integration
@pytest.mark.mobile
def test_project_creation_mobile_accessible(
    browser_context_mobile, api_client, env_config
):
    """
    Verify project created via API is accessible on mobile viewport.
    Uses iPhone 14 emulation via Playwright device profiles.
    """
    project_data = ProjectFactory.generate(tenant_id=env_config.tenant_id)
    project = create_project_via_api(api_client, project_data)
    project_id = project["id"]

    try:
        mobile_page = MobileProjectsPage(browser_context_mobile)
        mobile_page.navigate_to_projects(
            env_config.base_url,
            os.getenv("TEST_EMAIL", "admin@company1.com"),
            os.getenv("TEST_PASSWORD", "password123"),
        )

        assert mobile_page.is_project_visible(project_data["name"]), (
            f"Project '{project_data['name']}' visible on desktop "
            f"but not on mobile viewport"
        )
    finally:
        delete_project_via_api(api_client, project_id)


@pytest.mark.integration
@pytest.mark.parametrize(
    "browserstack_context",
    [
        {"browser": "chrome", "os": "Windows", "os_version": "11"},
        {"browser": "firefox", "os": "Windows", "os_version": "11"},
    ],
    indirect=True,
)
def test_project_creation_cross_browser(
    browserstack_context, api_client, env_config
):
    """
    Cross-browser verification using BrowserStack.
    Runs on Chrome and Firefox in parallel via parametrize.
    """
    project_data = ProjectFactory.generate(tenant_id=env_config.tenant_id)
    project = create_project_via_api(api_client, project_data)
    project_id = project["id"]

    try:
        page = browserstack_context
        login_page = LoginPage(page)
        login_page.login_as(
            env_config.base_url,
            os.getenv("TEST_EMAIL", "admin@company1.com"),
            os.getenv("TEST_PASSWORD", "password123"),
        )

        projects_page = ProjectsPage(page)
        projects_page.navigate_to(env_config.base_url)
        card = projects_page.find_project_card(project_data["name"])
        assert card is not None, (
            f"Project not visible on browser {browserstack_context}"
        )
    finally:
        delete_project_via_api(api_client, project_id)
