"""Web tier: start the app under test and drive Playwright probes against it.

Runs ONLY inside the web worker image (`workflo-worker-web:latest`), which
ships Playwright + Chromium. The base image never imports this module —
the `web` probe group gates execution in the worker executor.
"""

from __future__ import annotations
