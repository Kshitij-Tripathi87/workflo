from playwright.sync_api import expect
from workflo.ui.pages.base_page import BasePage


class DashboardPage(BasePage):
    URL_PATH = "/dashboard"

    def navigate_to(self, base_url: str):
        self.navigate(f"{base_url}{self.URL_PATH}")

    def welcome_message_visible(self) -> bool:
        try:
            expect(
                self.page.locator("[data-testid='welcome-message']")
            ).to_be_visible(timeout=10000)
            return True
        except:
            return False

    def get_welcome_text(self) -> str:
        return self.page.locator(
            "[data-testid='welcome-message']"
        ).text_content()

    def navigate_to_projects(self):
        self.page.locator("[data-testid='nav-projects']").click()
        self.page.wait_for_load_state("networkidle", timeout=15000)
