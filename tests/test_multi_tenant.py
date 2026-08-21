import os
import pytest
from playwright.sync_api import expect
from workflo.ui.pages.login_page import LoginPage
from workflo.ui.pages.dashboard_page import DashboardPage
from workflo.ui.pages.projects_page import ProjectsPage


def test_tenant_scoped_data_visibility(browser_context, env_config):
    page = browser_context
    email = os.getenv("TENANT_USER_EMAIL", "user@company2.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(page)
    login_page.login_as(env_config.base_url, email, password)

    dashboard = DashboardPage(page)
    assert dashboard.welcome_message_visible()

    projects_page = ProjectsPage(page)
    projects_page.navigate_to(env_config.base_url)
    projects_page.wait_for_data_testid("project-list")

    cards = page.locator("[data-testid='project-card']").all()
    assert len(cards) > 0, "No projects visible for this tenant"

    for card in cards:
        company = card.locator("[data-testid='project-card-company']")
        text = company.text_content()
        assert "Company2" in text or "Globex" in text, (
            f"Tenant isolation breach: project contains '{text}' "
            f"but user belongs to Company2"
        )


def test_tenant_cannot_see_other_tenant_projects(browser_context, env_config):
    page = browser_context
    email = os.getenv("COMPANY1_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(page)
    login_page.login_as(env_config.base_url, email, password)

    projects_page = ProjectsPage(page)
    projects_page.navigate_to(env_config.base_url)

    cards = page.locator("[data-testid='project-card']").all()
    for card in cards:
        company = card.locator("[data-testid='project-card-company']")
        text = company.text_content()
        assert "Company2" not in text and "Globex" not in text, (
            f"Security breach: Company1 user sees Company2 project: {text}"
        )


def test_role_based_access_employee(browser_context, env_config):
    page = browser_context
    email = os.getenv("EMPLOYEE_EMAIL", "employee@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(page)
    login_page.login_as(env_config.base_url, email, password)

    assert page.locator("[data-testid='create-project-btn']").is_hidden(), (
        "Employee should not see create project button"
    )


def test_role_based_access_admin(browser_context, env_config):
    page = browser_context
    email = os.getenv("TEST_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(page)
    login_page.login_as(env_config.base_url, email, password)

    expect(page.locator("[data-testid='create-project-btn']")).to_be_visible()
    expect(page.locator("[data-testid='manage-users-btn']")).to_be_visible()
