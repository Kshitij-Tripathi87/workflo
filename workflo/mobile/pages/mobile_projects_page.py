from workflo.ui.pages.base_page import BasePage


class MobileProjectsPage(BasePage):
    def navigate_to_projects(self, base_url: str, email: str, password: str):
        self.navigate(f"{base_url}/login")
        self.fill_testid("email-input", email)
        self.fill_testid("password-input", password)
        self.click_testid("login-btn")
        self.page.wait_for_url("**/dashboard**", timeout=20000)

        self.wait_for_data_testid("nav-projects")
        self.click_testid("nav-projects")
        self.page.wait_for_load_state("networkidle", timeout=20000)

    def is_project_visible(self, name: str) -> bool:
        try:
            self.wait_for_loading_complete()
            cards = self.page.locator(
                "[data-testid='project-card'], [data-testid='project-card-mobile']"
            ).all()
            for card in cards:
                if name in card.text_content():
                    return True
            return False
        except Exception:
            return False
