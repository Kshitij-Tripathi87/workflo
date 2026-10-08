"""Web-stage orchestration for the worker: resolve config, start the app,
run Playwright probes, stop the app, and produce the report payload.

The workflo.yaml contract (target repo's root, not Workflo's own config):

    web:
      start_command: "python app.py"
      port: 5000

Resolution precedence (spec/env wins over workflo.yaml, since the CLI /
API flags are explicit user intent):
    1. WORKFLO_START_COMMAND / WORKFLO_WEB_PORT env vars (set by the
       executor from the run spec's env)
    2. workflo.yaml in the cloned repo root
    3. neither -> fail closed with an actionable error naming what's
       missing. No framework auto-detection (package.json scripts,
       Procfile sniffing) — explicit config only, by plan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from workflo_worker.web.app_starter import (
    start_app_under_test,
    stop_app_under_test,
)
from workflo_worker.web.probes import run_web_probes


class WebConfigError(Exception):
    """Raised when the web tier is requested but its config is unresolvable."""


def resolve_web_config(repo_path: str, env: Optional[dict] = None) -> dict:
    """Resolve (start_command, port) for the web tier, failing fast.

    Args:
        repo_path: the cloned repo root (workflo.yaml is read from here).
        env: dict of env var values (defaults to os.environ). Keys honored:
            WORKFLO_START_COMMAND, WORKFLO_WEB_PORT.

    Returns:
        {"start_command": str, "port": int}

    Raises:
        WebConfigError: web tier requested but neither source provides
            the required values. Message names exactly what's missing.
    """
    env = env if env is not None else os.environ

    start_command = env.get("WORKFLO_START_COMMAND")
    port_raw = env.get("WORKFLO_WEB_PORT")

    # Fall back to workflo.yaml in the repo root if env is absent.
    if not start_command or not port_raw:
        yaml_cfg = _read_workflo_yaml(repo_path)
        if not start_command:
            start_command = yaml_cfg.get("start_command")
        if not port_raw:
            port_raw = yaml_cfg.get("port")

    missing = []
    if not start_command:
        missing.append("start_command")
    if not port_raw:
        missing.append("port")

    if missing:
        raise WebConfigError(
            f"web tier requested but missing: {', '.join(missing)}. "
            f"Provide them via WORKFLO_START_COMMAND/WORKFLO_WEB_PORT env, "
            f"the CLI's --start-command/--port flags, or a workflo.yaml in "
            f"the repo root with:\n"
            f"  web:\n"
            f"    start_command: <cmd>\n"
            f"    port: <n>"
        )

    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        raise WebConfigError(f"web port is not an integer: {port_raw!r}")
    if not (1 <= port <= 65535):
        raise WebConfigError(f"web port out of range: {port}")

    return {"start_command": start_command, "port": port}


def _read_workflo_yaml(repo_path: str) -> dict:
    """Read the `web:` section of workflo.yaml from the repo root.

    Returns an empty dict when absent or invalid — resolution falls back
    to env/CLI flags, and if those are also absent, resolve_web_config
    raises with a message naming exactly what's missing.
    """
    candidates = ["workflo.yaml", "workflo.yml"]
    repo = Path(repo_path)
    for name in candidates:
        path = repo / name
        if not path.is_file():
            continue
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(data, dict) and isinstance(data.get("web"), dict):
            web = data["web"]
            return {
                "start_command": web.get("start_command"),
                "port": web.get("port"),
            }
    return {}


def run_web_stage(repo_path: str, env: Optional[dict] = None) -> dict:
    """Run the full web stage and return the WORKFLO_WEB_PROBES payload.

    The payload is ALWAYS produced (even on config/app/probe failures) —
    the executor's receipt distinguishes "web tier not requested"
    (no line) from "web tier ran and failed" (line with failures). This
    matches the model-teardown discipline: None vs False are different
    facts.

    Returns:
        {"base_url": str, "probes": [...], "app_start_error": str|None}
    """
    try:
        cfg = resolve_web_config(repo_path, env)
    except WebConfigError as e:
        return {"base_url": "", "probes": [], "app_start_error": str(e)}

    base_url = f"http://127.0.0.1:{cfg['port']}"
    proc = None
    try:
        proc = start_app_under_test(repo_path, cfg["start_command"], cfg["port"])
        probes = run_web_probes(base_url)
        return {"base_url": base_url, "probes": probes, "app_start_error": None}
    except Exception as e:
        # App crashed / port never opened / probe infrastructure failed —
        # all valid reportable outcomes.
        return {
            "base_url": base_url,
            "probes": [],
            "app_start_error": f"{type(e).__name__}: {e}",
        }
    finally:
        stop_app_under_test(proc)
