from playwright.sync_api import Locator


class ProjectCardComponent:
    def __init__(self, locator: Locator):
        self.locator = locator

    def get_name(self) -> str:
        return self.locator.locator(
            "[data-testid='project-card-name']"
        ).text_content()

    def get_status(self) -> str:
        return self.locator.locator(
            "[data-testid='project-card-status']"
        ).text_content()

    def get_company(self) -> str:
        return self.locator.locator(
            "[data-testid='project-card-company']"
        ).text_content()

    def click(self):
        self.locator.locator("[data-testid='project-link']").click()
