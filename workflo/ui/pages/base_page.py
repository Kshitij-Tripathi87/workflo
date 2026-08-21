from playwright.sync_api import Page, expect


class BasePage:
    def __init__(self, page: Page):
        self.page = page
        self.timeout = 15000

    def navigate(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle", timeout=self.timeout)

    def wait_for_selector(self, selector: str, state="visible"):
        self.page.locator(selector).wait_for(state=state, timeout=self.timeout)

    def wait_for_data_testid(self, testid: str, state="visible"):
        self.page.locator(f"[data-testid='{testid}']").wait_for(
            state=state, timeout=self.timeout
        )

    def click_testid(self, testid: str):
        self.page.locator(f"[data-testid='{testid}']").click()

    def fill_testid(self, testid: str, value: str):
        self.page.locator(f"[data-testid='{testid}']").fill(value)

    def is_mobile_view(self) -> bool:
        viewport = self.page.viewport_size
        return viewport["width"] < 768

    def take_screenshot(self, name: str):
        self.page.screenshot(
            path=f"reports/screenshots/{name}.png", full_page=True
        )

    def wait_for_loading_complete(self):
        try:
            self.page.locator("[data-testid='loading-spinner']").wait_for(
                state="hidden", timeout=10000
            )
        except:
            pass
