"""Playwright browser probes — the `web` tier's checks.

A `page.goto` failure is a VALID, reportable outcome (the app under test
is broken), not a Workflo bug. Every probe result is recorded as
{name, passed, detail}; the run never crashes out of the probe loop —
the same error-handling discipline as the model adapter.

The two default probes are deliberately independent:
  - page_loads        : did the page return an HTTP OK?
  - no_console_errors : did the page emit any console.error messages?

A broken page with a JS error that still loads fails `no_console_errors`
but PASSES `page_loads` — proving the two checks aren't accidentally
coupled (a page that loads but logs errors is a real, common bug).
"""

from __future__ import annotations

from typing import Callable, Optional


def run_web_probes(
    base_url: str,
    timeout_ms: int = 10000,
    _launch_override: Optional[Callable] = None,
) -> list[dict]:
    """Run browser probes against `base_url` and return per-probe results.

    `_launch_override` exists for tests: it receives (playwright_context)
    and returns a browser, letting unit tests inject a fake Playwright
    without shipping a real Chromium in CI.

    Returns a list of dicts: {name, passed, detail}. Never raises for
    probe failures — a broken app under test is a reportable outcome.
    """
    results: list[dict] = []

    # Import inside the function: the module must be importable on the
    # BASE worker image too (which has no Playwright) — only the web
    # image has it installed, and only the web tier calls this function.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return [{
            "name": "playwright_available",
            "passed": False,
            "detail": f"playwright not installed in this worker image: {e}",
        }]

    with sync_playwright() as p:
        if _launch_override is not None:
            browser = _launch_override(p)
        else:
            browser = p.chromium.launch()
        page = browser.new_page()
        console_errors: list[str] = []

        def _on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)

        page.on("console", _on_console)

        # Probe 1: page_loads — must not crash the whole run on failure.
        try:
            response = page.goto(base_url, timeout=timeout_ms)
            results.append({
                "name": "page_loads",
                "passed": bool(response and response.ok),
                "detail": f"status={response.status if response else 'no response'}",
            })
        except Exception as e:
            results.append({
                "name": "page_loads",
                "passed": False,
                "detail": str(e),
            })

        # Probe 2: no_console_errors — independent of page_loads.
        results.append({
            "name": "no_console_errors",
            "passed": len(console_errors) == 0,
            "detail": list(console_errors) if console_errors else "no console errors",
        })

        browser.close()

    return results
