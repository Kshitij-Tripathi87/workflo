import os
import pytest
from playwright.sync_api import expect
from workflo.ui.pages.login_page import LoginPage
from workflo.ui.pages.dashboard_page import DashboardPage


def login_user(page, email, password, base_url):
    login_page = LoginPage(page)
    login_page.login_as(base_url, email, password)


def test_standard_user_login(browser_context, env_config):
    page = browser_context
    email = os.getenv("TEST_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_user(page, email, password, env_config.base_url)

    assert "/dashboard" in page.url, f"Expected /dashboard in URL, got {page.url}"
    dashboard = DashboardPage(page)
    assert dashboard.welcome_message_visible(), "Welcome message not visible"


def test_login_form_validation(browser_context, env_config):
    page = browser_context
    login_page = LoginPage(page)
    login_page.navigate_to(env_config.base_url)

    login_page.click_login()

    expect(page.locator("[data-testid='email-error']")).to_be_visible()
    expect(page.locator("[data-testid='password-error']")).to_be_visible()


def test_login_invalid_credentials(browser_context, env_config):
    page = browser_context
    login_page = LoginPage(page)
    login_page.navigate_to(env_config.base_url)
    login_page.fill_email("invalid@test.com")
    login_page.fill_password("wrongpass")
    login_page.click_login()

    error = page.locator("[data-testid='login-error']")
    expect(error).to_be_visible(timeout=10000)
    assert "Invalid" in error.text_content()


def test_login_redirect_when_already_authenticated(browser_context, env_config):
    page = browser_context
    email = os.getenv("TEST_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_user(page, email, password, env_config.base_url)
    dashboard = DashboardPage(page)
    assert dashboard.welcome_message_visible()

    login_page = LoginPage(page)
    login_page.navigate_to(env_config.base_url)
    page.wait_for_load_state("networkidle", timeout=10000)

    assert "/dashboard" in page.url, (
        "User was not redirected to dashboard when already authenticated"
    )


@pytest.mark.skipif(
    not os.getenv("TEST_2FA_CODE"),
    reason="TEST_2FA_CODE env var not set",
)
def test_login_with_two_factor_auth(browser_context, env_config):
    page = browser_context
    email = os.getenv("TEST_EMAIL", "admin@company1.com")
    password = os.getenv("TEST_PASSWORD", "password123")

    login_page = LoginPage(page)
    login_page.login_as(env_config.base_url, email, password)

    if "2fa" in page.url or page.locator("#2fa-code").is_visible():
        page.fill("#2fa-code", os.getenv("TEST_2FA_CODE"))
        page.click("#verify-2fa-btn")
        page.wait_for_url("**/dashboard**", timeout=15000)

    dashboard = DashboardPage(page)
    assert dashboard.welcome_message_visible()
