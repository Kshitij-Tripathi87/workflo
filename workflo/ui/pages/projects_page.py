from workflo.ui.pages.base_page import BasePage


class ProjectsPage(BasePage):
    URL_PATH = "/projects"

    def navigate_to(self, base_url: str):
        self.navigate(f"{base_url}{self.URL_PATH}")
        self.wait_for_loading_complete()
        self.wait_for_data_testid("project-list")

    def search_project(self, name: str):
        self.fill_testid("search-projects", name)
        self.page.wait_for_timeout(500)
        self.page.wait_for_load_state("networkidle", timeout=10000)

    def find_project_card(self, name: str):
        cards = self.page.locator("[data-testid='project-card']").all()
        for card in cards:
            if name in card.text_content():
                return card
        return None

    def open_project(self, name: str):
        card = self.find_project_card(name)
        if card is None:
            raise AssertionError(f"Project '{name}' not found in UI")
        card.locator("[data-testid='project-link']").click()
        self.page.wait_for_load_state("networkidle", timeout=15000)

    def get_project_details(self):
        return {
            "name": self.page.locator(
                "[data-testid='project-name']"
            ).text_content(),
            "status": self.page.locator(
                "[data-testid='project-status']"
            ).text_content(),
            "description": self.page.locator(
                "[data-testid='project-description']"
            ).text_content(),
        }
