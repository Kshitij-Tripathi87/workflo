"""Browser adapter — launches containerized browsers for test execution."""

from typing import Optional
from workflo_schema import BrowserMode


class BrowserAdapter:
    """Abstracts Playwright browser launching — local container or remote grid."""

    def __init__(self, mode: BrowserMode = BrowserMode.CONTAINER, remote_url: Optional[str] = None):
        self.mode = mode
        self.remote_url = remote_url

    def launch(self):
        """Return a Playwright browser instance based on the mode."""
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()

        if self.mode == BrowserMode.REAL_FLEET and self.remote_url:
            # Connect to remote grid (BrowserStack / Sauce Labs / private grid)
            browser = p.chromium.connect_over_cdp(self.remote_url)
        else:
            # Launch local containerized browser
            browser = p.chromium.launch(headless=True)

        return p, browser

    @staticmethod
    def shutdown(p, browser):
        """Cleanly close the browser and Playwright instance."""
        browser.close()
        p.stop()
