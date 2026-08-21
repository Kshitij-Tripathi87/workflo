"""Remote grid adapter — connects to BrowserStack, Sauce Labs, or a private Playwright grid."""

from typing import Optional


class GridAdapter:
    """Builds connection URLs and capabilities for remote browser grids."""

    def __init__(self, provider: str = "browserstack", username: Optional[str] = None, access_key: Optional[str] = None):
        self.provider = provider
        self.username = username
        self.access_key = access_key

    def build_endpoint(self) -> str:
        if self.provider == "browserstack":
            return f"wss://cdp.browserstack.com/v2?user={self.username}&key={self.access_key}"
        elif self.provider == "saucelabs":
            return f"ondemand.saucelabs.com/wd/hub"
        elif self.provider == "private":
            return f"http://{self.username}:{self.access_key}@grid:4444"
        raise ValueError(f"Unknown grid provider: {self.provider}")

    def build_capabilities(self, browser: str = "chrome", device: Optional[str] = None) -> dict:
        caps = {"browserName": browser}
        if device and self.provider == "browserstack":
            caps["bstack:options"] = {"deviceName": device, "realMobile": True}
        return caps
