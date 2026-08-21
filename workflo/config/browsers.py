BROWSER_MATRIX = [
    {
        "browser": "chromium",
        "os": "Windows",
        "os_version": "11",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "browser": "firefox",
        "os": "Windows",
        "os_version": "11",
        "viewport": {"width": 1920, "height": 1080},
    },
    {
        "browser": "webkit",
        "os": "OS X",
        "os_version": "Monterey",
        "viewport": {"width": 1440, "height": 900},
    },
]

MOBILE_DEVICE_MATRIX = [
    {
        "device": "iPhone 14",
        "os_version": "16",
        "real_mobile": True,
        "viewport": {"width": 390, "height": 844},
    },
    {
        "device": "Samsung Galaxy S23",
        "os_version": "13",
        "real_mobile": True,
        "viewport": {"width": 360, "height": 780},
    },
    {
        "device": "iPad Pro 12.9",
        "os_version": "16",
        "real_mobile": False,
        "viewport": {"width": 1024, "height": 1366},
    },
]


def get_browserstack_capabilities(browser_config, test_name, build_name):
    capabilities = {
        "browser": browser_config.get("browser", "chrome"),
        "browser_version": "latest",
        "os": browser_config.get("os", "Windows"),
        "os_version": browser_config.get("os_version", "11"),
        "name": test_name,
        "build": build_name,
        "browserstack.networkLogs": True,
        "browserstack.consoleLogs": "errors",
        "browserstack.video": True,
    }

    if "device" in browser_config:
        capabilities["device"] = browser_config["device"]
        capabilities["real_mobile"] = browser_config.get("real_mobile", True)

    return capabilities
