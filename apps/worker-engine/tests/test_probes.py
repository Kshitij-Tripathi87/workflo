"""Unit tests for the web tier's probes module.

Key contract: a page.goto failure is a VALID, reportable outcome (the app
under test is broken) — it must appear as a failed probe, not crash the
whole run. And page_loads / no_console_errors must stay independent.
"""

from __future__ import annotations

import pytest

from workflo_worker.web.probes import run_web_probes


class FakePage:
    """Minimal fake page: collects console handlers, simulates goto + console."""

    def __init__(self, goto_response=None, goto_error=None, console_errors=(), emit_on_goto=None):
        self._goto_response = goto_response
        self._goto_error = goto_error
        self._console_errors = list(console_errors)
        self.console_handler = None
        self.goto_calls = 0
        self._emit_on_goto = list(emit_on_goto or [])

    def on(self, event, handler):
        if event == "console":
            self.console_handler = handler

    def goto(self, url, timeout):
        self.goto_calls += 1
        if self._emit_on_goto:
            for e in self._emit_on_goto:
                self.emit_console(e[0], e[1])
        if self._goto_error is not None:
            raise self._goto_error
        return self._goto_response

    def emit_console(self, msg_type, text):
        if self.console_handler is not None:
            handler = self.console_handler
            msg_type_ = msg_type
            text_ = text

            class Msg:
                type = msg_type_
                text = text_

            handler(Msg())


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, browser):
        self._browser = browser

    def chromium(self):
        return self._browser


class FakeResponse:
    def __init__(self, status):
        self.status = status
        self.ok = 200 <= status < 400


class TestRunWebProbes:
    def test_all_pass_on_healthy_app(self):
        """Healthy app: both default probes pass."""
        page = FakePage(goto_response=FakeResponse(200))
        browser = FakeBrowser(page)
        p = FakePlaywright(browser)

        results = run_web_probes("http://127.0.0.1:5000", _launch_override=lambda pw: browser)

        by_name = {r["name"]: r for r in results}
        assert by_name["page_loads"]["passed"] is True
        assert by_name["no_console_errors"]["passed"] is True

    def test_goto_failure_is_a_failed_probe_not_a_crash(self):
        """A page.goto exception (app broken / connection refused) must be
        recorded as a failed probe — run_web_probes must NOT raise."""
        page = FakePage(goto_error=TimeoutError("navigation timed out"))
        browser = FakeBrowser(page)
        p = FakePlaywright(browser)

        results = run_web_probes("http://127.0.0.1:5000", _launch_override=lambda pw: browser)

        by_name = {r["name"]: r for r in results}
        assert by_name["page_loads"]["passed"] is False
        assert "timed out" in by_name["page_loads"]["detail"]

    def test_console_errors_caught_independently_of_page_load(self):
        """A page that loads fine but logs a console error fails
        no_console_errors while PASSING page_loads — the two probes must
        not be accidentally coupled."""
        # Console errors fire DURING goto — exactly when a real page would
        # log them (before the no_console_errors check reads the list).
        page = FakePage(
            goto_response=FakeResponse(200),
            emit_on_goto=[
                ("error", "TypeError: x is not a function"),
                ("error", "Failed to load resource: 404"),
            ],
        )
        browser = FakeBrowser(page)

        def launch(pw):
            return browser

        results = run_web_probes("http://127.0.0.1:5000", _launch_override=launch)
        by_name = {r["name"]: r for r in results}
        assert by_name["page_loads"]["passed"] is True
        assert by_name["no_console_errors"]["passed"] is False
        assert len(by_name["no_console_errors"]["detail"]) == 2

    def test_missing_playwright_reports_failed_probe(self):
        """On an image WITHOUT playwright (base image), the module must not
        raise at import or run time — it reports a failed probe instead."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "playwright.sync_api":
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(builtins, "__import__", fake_import)
            results = run_web_probes("http://127.0.0.1:5000")

        assert results[0]["name"] == "playwright_available"
        assert results[0]["passed"] is False
